"""Unit tests for Phase 5: Human-in-the-Loop (HITL) approval and rejection endpoints."""

import uuid
from datetime import UTC, datetime

import httpx
import pytest

from apps.api.database import get_db
from apps.api.main import app
from apps.api.models import AgentTrace, Incident, IncidentStatus
from apps.api.routers.approvals import get_github_client


class _ExecuteResult:
    def __init__(self, scalar_val: object = None) -> None:
        self._scalar_val = scalar_val

    def scalar_one_or_none(self) -> object:
        return self._scalar_val


class FakeApprovalSession:
    def __init__(self, incident: Incident | None) -> None:
        self.incident = incident
        self.added_traces: list[AgentTrace] = []

    def add(self, obj: object) -> None:
        if isinstance(obj, AgentTrace):
            self.added_traces.append(obj)

    async def execute(self, stmt: object) -> _ExecuteResult:
        return _ExecuteResult(scalar_val=self.incident)

    async def commit(self) -> None:
        return None

    async def refresh(self, obj: object) -> None:
        return None

    async def rollback(self) -> None:
        return None


class FakeGitHubClient:
    def __init__(self) -> None:
        self.created_branch: str | None = None
        self.committed_files: dict[str, str] = {}
        self.opened_pr: dict[str, str] = {}

    async def fetch_file_contents(
        self, repo_owner: str, repo_name: str, file_path: str, ref: str = "main"
    ) -> str:
        return "def divide(a: int, b: int) -> float:\n    return a / b\n"

    async def create_branch(
        self, repo_owner: str, repo_name: str, branch_name: str, base_branch: str = "main"
    ) -> str:
        self.created_branch = branch_name
        return "base-sha-123"

    async def commit_patched_files(
        self,
        repo_owner: str,
        repo_name: str,
        branch_name: str,
        files: dict[str, str],
        commit_message: str,
    ) -> str:
        self.committed_files = files
        return "commit-sha-456"

    async def open_pull_request(
        self,
        repo_owner: str,
        repo_name: str,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> str:
        self.opened_pr = {"head": head_branch, "base": base_branch, "title": title}
        return "https://github.com/acme/billing/pull/42"


def _make_incident(status: IncidentStatus = IncidentStatus.AWAITING_APPROVAL) -> Incident:
    inc_id = uuid.uuid4()
    now = datetime.now(UTC)
    return Incident(
        id=inc_id,
        fingerprint="a" * 64,
        repo_owner="acme",
        repo_name="billing",
        base_branch="main",
        error_type="ZeroDivisionError",
        error_message="division by zero",
        stack_trace='File "src/calc.py", line 2, in divide',
        status=status,
        proposed_diff=(
            "--- a/src/calc.py\n"
            "+++ b/src/calc.py\n"
            "@@ -1,2 +1,2 @@\n"
            " def divide(a: int, b: int) -> float:\n"
            "-    return a / b\n"
            "+    return 0.0 if b == 0 else a / b\n"
        ),
        patch_explanation="Guard zero divisor",
        retry_count=0,
        total_tokens=150,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_approve_incident_opens_pr_and_updates_status() -> None:
    incident = _make_incident(IncidentStatus.AWAITING_APPROVAL)
    fake_db = FakeApprovalSession(incident)
    fake_gh = FakeGitHubClient()

    async def override_db() -> object:
        yield fake_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_github_client] = lambda: fake_gh

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/v1/incidents/{incident.id}/approve")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == IncidentStatus.APPROVED_PR_OPENED.value
            assert data["pr_url"] == "https://github.com/acme/billing/pull/42"
            assert fake_gh.created_branch == f"patchwork/fix-{incident.id}"
            assert "0.0 if b == 0 else a / b" in fake_gh.committed_files["src/calc.py"]
            assert fake_gh.opened_pr["base"] == "main"
            assert len(fake_db.added_traces) == 1
            assert fake_db.added_traces[0].step_name == "hitl_approved"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_approve_invalid_state_returns_409_and_missing_returns_404() -> None:
    incident = _make_incident(IncidentStatus.QUEUED)
    fake_db = FakeApprovalSession(incident)

    async def override_db() -> object:
        yield fake_db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_github_client] = lambda: FakeGitHubClient()

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/v1/incidents/{incident.id}/approve")
            assert resp.status_code == 409

            fake_db.incident = None
            resp_404 = await client.post(f"/v1/incidents/{uuid.uuid4()}/approve")
            assert resp_404.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_reject_incident_updates_status_and_logs_reason() -> None:
    incident = _make_incident(IncidentStatus.AWAITING_APPROVAL)
    fake_db = FakeApprovalSession(incident)

    async def override_db() -> object:
        yield fake_db

    app.dependency_overrides[get_db] = override_db

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/v1/incidents/{incident.id}/reject",
                json={"reason": "Should raise ValueError instead of returning 0.0"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == IncidentStatus.REJECTED.value
            assert len(fake_db.added_traces) == 1
            assert "Should raise ValueError" in fake_db.added_traces[0].thought_summary

            # Second reject returns 409 Conflict
            resp_again = await client.post(
                f"/v1/incidents/{incident.id}/reject",
                json={"reason": "Duplicate reject"},
            )
            assert resp_again.status_code == 409
    finally:
        app.dependency_overrides.clear()
