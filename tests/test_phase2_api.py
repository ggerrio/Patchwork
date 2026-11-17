"""Unit tests for Phase 2: Ingestion API, Redis deduplication, and async GitHub client."""

import base64
import json
import uuid
from datetime import UTC, datetime

import httpx
import pytest

from apps.api.database import get_db
from apps.api.main import app
from apps.api.models import AgentTrace, Incident, IncidentStatus
from apps.api.routers.incidents import get_enqueue_fn
from apps.api.services.deduplicator import (
    IncidentDeduplicator,
    compute_fingerprint,
    extract_location_from_stack_trace,
)
from apps.api.services.github_client import GitHubClient, GitHubClientError
from apps.api.services.incident_service import get_redis_client


class FakeRedis:
    """In-memory async Redis stub supporting `set(..., nx=True, ex=...)` and `delete`."""

    def __init__(self) -> None:
        self.store: dict[str, tuple[str, int | None]] = {}

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int | None = None) -> bool:
        if nx and key in self.store:
            return False
        self.store[key] = (value, ex)
        return True

    async def delete(self, key: str) -> int:
        return 1 if self.store.pop(key, None) is not None else 0


class _ScalarResult:
    def __init__(self, items: list[object]) -> None:
        self._items = items

    def all(self) -> list[object]:
        return self._items


class _ExecuteResult:
    def __init__(self, items: list[object] | None = None, scalar_val: object = None) -> None:
        self._items = items or []
        self._scalar_val = scalar_val

    def scalars(self) -> _ScalarResult:
        return _ScalarResult(self._items)

    def scalar_one(self) -> object:
        return self._scalar_val

    def scalar_one_or_none(self) -> object:
        return self._scalar_val


class FakeAsyncSession:
    """Minimal async SQLAlchemy session stub for API router unit tests."""

    def __init__(self) -> None:
        self.incidents: dict[uuid.UUID, Incident] = {}

    def add(self, obj: object) -> None:
        if isinstance(obj, Incident):
            if obj.id is None:
                obj.id = uuid.uuid4()
            now = datetime.now(UTC)
            obj.created_at = obj.created_at or now
            obj.updated_at = obj.updated_at or now
            obj.retry_count = obj.retry_count or 0
            obj.total_tokens = obj.total_tokens or 0
            obj.traces = []
            self.incidents[obj.id] = obj

    async def commit(self) -> None:
        return None

    async def refresh(self, obj: object) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def execute(self, stmt: object) -> _ExecuteResult:
        stmt_str = str(stmt)
        if "count(" in stmt_str.lower():
            return _ExecuteResult(scalar_val=len(self.incidents))
        if "WHERE incidents.id =" in stmt_str:
            # Extract bound UUID from compiled params if present
            params = stmt.compile().params  # type: ignore[attr-defined]
            target_id = next(iter(params.values()), None)
            return _ExecuteResult(scalar_val=self.incidents.get(target_id))
        return _ExecuteResult(items=list(self.incidents.values()))


def test_fingerprint_extraction_and_determinism() -> None:
    trace = (
        "Traceback (most recent call last):\n"
        '  File "app/main.py", line 10, in handler\n'
        '  File "app/billing.py", line 42, in charge\n'
        "ZeroDivisionError: division by zero"
    )
    file_path, line_no = extract_location_from_stack_trace(trace)
    assert file_path == "app/billing.py"
    assert line_no == 42

    fp1 = compute_fingerprint("ZeroDivisionError", file_path, line_no)
    fp2 = compute_fingerprint("ZeroDivisionError", file_path, line_no)
    assert fp1 == fp2
    assert len(fp1) == 64


@pytest.mark.asyncio
async def test_deduplicator_acquire_and_release() -> None:
    redis = FakeRedis()
    dedup = IncidentDeduplicator(redis_client=redis, ttl_seconds=3600)  # type: ignore[arg-type]

    assert await dedup.acquire_lock("abc123") is True
    assert redis.store["patchwork:incident:dedup:abc123"] == ("1", 3600)
    assert await dedup.acquire_lock("abc123") is False

    await dedup.release_lock("abc123")
    assert await dedup.acquire_lock("abc123") is True


@pytest.mark.asyncio
async def test_incident_ingestion_dedup_and_queries() -> None:
    fake_db = FakeAsyncSession()
    fake_redis = FakeRedis()
    enqueued_ids: list[uuid.UUID] = []

    async def fake_enqueue(incident_id: uuid.UUID) -> str:
        enqueued_ids.append(incident_id)
        return "job-123"

    async def override_db() -> object:
        yield fake_db

    async def override_redis() -> object:
        yield fake_redis

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_redis_client] = override_redis
    app.dependency_overrides[get_enqueue_fn] = lambda: fake_enqueue

    payload = {
        "repo_owner": "acme",
        "repo_name": "billing",
        "base_branch": "main",
        "error_type": "KeyError",
        "error_message": "'currency'",
        "stack_trace": 'Traceback:\n  File "src/calc.py", line 18, in total\nKeyError: \'currency\'',
    }

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp1 = await client.post("/v1/incidents", json=payload)
            assert resp1.status_code == 202
            body1 = resp1.json()
            assert body1["deduplicated"] is False
            assert body1["status"] == "QUEUED"
            incident_id = body1["id"]
            assert len(enqueued_ids) == 1

            # Duplicate within TTL
            resp2 = await client.post("/v1/incidents", json=payload)
            assert resp2.status_code == 200
            body2 = resp2.json()
            assert body2["deduplicated"] is True
            assert body2["status"] == "DUPLICATE_IGNORED"
            assert body2["fingerprint"] == body1["fingerprint"]
            assert len(enqueued_ids) == 1

            # List incidents
            list_resp = await client.get("/v1/incidents")
            assert list_resp.status_code == 200
            assert list_resp.json()["total"] == 1

            # Attach a trace and fetch detail
            stored = fake_db.incidents[uuid.UUID(incident_id)]
            stored.traces.append(
                AgentTrace(
                    id=uuid.uuid4(),
                    incident_id=stored.id,
                    step_name="triage_node",
                    thought_summary="Located KeyError in src/calc.py:18",
                    tool_output="src/calc.py:18",
                    tokens_used=120,
                    latency_ms=450,
                    created_at=datetime.now(UTC),
                )
            )
            detail_resp = await client.get(f"/v1/incidents/{incident_id}")
            assert detail_resp.status_code == 200
            detail = detail_resp.json()
            assert detail["status"] == IncidentStatus.QUEUED.value
            assert len(detail["traces"]) == 1
            assert detail["traces"][0]["step_name"] == "triage_node"

            # Missing incident returns 404
            missing_resp = await client.get(f"/v1/incidents/{uuid.uuid4()}")
            assert missing_resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_github_client_operations() -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        path = request.url.path

        if request.method == "GET" and path.endswith("/contents/src/app.py"):
            encoded = base64.b64encode(b"print('hello')\n").decode("ascii")
            return httpx.Response(200, json={"content": encoded})
        if request.method == "GET" and path.endswith("/git/ref/heads/main"):
            return httpx.Response(200, json={"object": {"sha": "base-sha-111"}})
        if request.method == "POST" and path.endswith("/git/refs"):
            body = json.loads(request.content)
            assert body["ref"] == "refs/heads/patchwork/fix-1"
            return httpx.Response(201, json={"ref": body["ref"]})
        if request.method == "GET" and path.endswith("/git/ref/heads/patchwork/fix-1"):
            return httpx.Response(200, json={"object": {"sha": "branch-sha-222"}})
        if request.method == "GET" and path.endswith("/git/commits/branch-sha-222"):
            return httpx.Response(200, json={"tree": {"sha": "tree-sha-333"}})
        if request.method == "POST" and path.endswith("/git/blobs"):
            return httpx.Response(201, json={"sha": "blob-sha-444"})
        if request.method == "POST" and path.endswith("/git/trees"):
            return httpx.Response(201, json={"sha": "new-tree-sha-555"})
        if request.method == "POST" and path.endswith("/git/commits"):
            return httpx.Response(201, json={"sha": "new-commit-sha-666"})
        if request.method == "PATCH" and path.endswith("/git/refs/heads/patchwork/fix-1"):
            return httpx.Response(200, json={"object": {"sha": "new-commit-sha-666"}})
        if request.method == "POST" and path.endswith("/pulls"):
            return httpx.Response(201, json={"html_url": "https://github.com/acme/app/pull/7"})
        return httpx.Response(404, json={"message": "Not Found"})

    client = GitHubClient(token="ghp_test_token", transport=httpx.MockTransport(handler))

    content = await client.fetch_file_contents("acme", "app", "src/app.py", ref="main")
    assert content == "print('hello')\n"

    sha = await client.create_branch("acme", "app", "patchwork/fix-1", base_branch="main")
    assert sha == "base-sha-111"

    commit_sha = await client.commit_patched_files(
        "acme",
        "app",
        "patchwork/fix-1",
        {"src/app.py": "print('fixed')\n"},
        "fix: handle edge case",
    )
    assert commit_sha == "new-commit-sha-666"

    pr_url = await client.open_pull_request(
        "acme",
        "app",
        head_branch="patchwork/fix-1",
        base_branch="main",
        title="fix: handle edge case",
        body="Automated fix verified in E2B sandbox.",
    )
    assert pr_url == "https://github.com/acme/app/pull/7"

    with pytest.raises(GitHubClientError):
        await client.commit_patched_files("acme", "app", "main", {"a.py": "x"}, "bad")
