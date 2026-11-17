"""Unit tests for Phase 4: LangGraph autonomous healing workflow & E2B runner."""

import pytest

from apps.api.config import parse_arq_redis_settings
from apps.api.models import IncidentStatus
from apps.worker.graph.nodes import (
    FilePatch,
    NodeDependencies,
    PatchGenerationResult,
    PatchProposal,
)
from apps.worker.graph.state import AgentState
from apps.worker.graph.workflow import build_workflow
from apps.worker.sandbox.docker_runner import SandboxResult, _build_tar_archive


class FakeGitHubClient:
    async def fetch_file_contents(
        self, repo_owner: str, repo_name: str, file_path: str, ref: str = "main"
    ) -> str:
        return "def divide(a, b):\n    return a / b\n"


class FakeSandboxRunner:
    def __init__(self, results: list[SandboxResult]) -> None:
        self._results = list(results)
        self.calls = 0

    async def run_pytest(
        self,
        files: dict[str, str],
        test_command: str = "pytest -q",
        timeout_seconds: int = 120,
    ) -> SandboxResult:
        idx = min(self.calls, len(self._results) - 1)
        self.calls += 1
        return self._results[idx]


def _base_state() -> AgentState:
    return {
        "incident_id": "11111111-1111-1111-1111-111111111111",
        "repo_owner": "acme",
        "repo_name": "billing",
        "base_branch": "main",
        "error_type": "ZeroDivisionError",
        "error_message": "division by zero",
        "stack_trace": (
            "Traceback (most recent call last):\n"
            '  File "src/calc.py", line 2, in divide\n'
            "ZeroDivisionError: division by zero"
        ),
        "file_contents": {},
        "semantic_neighbors": [],
        "retry_count": 0,
        "max_retries": 3,
        "total_tokens": 0,
    }


@pytest.mark.asyncio
async def test_workflow_happy_path_awaits_approval() -> None:
    traces: list[tuple[str, int, int]] = []

    async def trace_logger(
        incident_id: str,
        step_name: str,
        thought_summary: str,
        tool_output: str | None,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
    ) -> None:
        traces.append((step_name, prompt_tokens, completion_tokens))

    async def patch_gen(state: AgentState) -> PatchGenerationResult:
        return PatchGenerationResult(
            proposal=PatchProposal(
                root_cause_explanation="Guard against b == 0 in divide()",
                unified_diff="",
                file_patches=[
                    FilePatch(
                        file_path="src/calc.py",
                        updated_content="def divide(a, b):\n    return 0.0 if b == 0 else a / b\n",
                    )
                ],
            ),
            prompt_tokens=100,
            completion_tokens=50,
        )

    async def neighbor_search(repo: str, query: str) -> list[dict[str, object]]:
        return [{"file_path": "src/calc.py", "symbol_name": "divide"}]

    sandbox = FakeSandboxRunner(
        [SandboxResult(passed=True, exit_code=0, stdout="1 passed", stderr="", duration_ms=250)]
    )
    deps = NodeDependencies(
        github_client=FakeGitHubClient(),  # type: ignore[arg-type]
        sandbox_runner=sandbox,  # type: ignore[arg-type]
        trace_logger=trace_logger,
        patch_generator=patch_gen,
        neighbor_search=neighbor_search,
    )

    workflow = build_workflow(deps)
    final_state = await workflow.ainvoke(_base_state())

    assert final_state["final_status"] == IncidentStatus.AWAITING_APPROVAL.value
    assert final_state["retry_count"] == 0
    assert final_state["total_tokens"] == 150
    assert "--- a/src/calc.py" in final_state["proposed_diff"]
    assert sandbox.calls == 1
    assert [t[0] for t in traces] == ["triage_node", "retrieve_node", "patch_node", "sandbox_node"]


@pytest.mark.asyncio
async def test_workflow_retries_and_self_corrects() -> None:
    attempts = 0

    async def noop_trace(*args: object) -> None:
        return None

    async def patch_gen(state: AgentState) -> PatchGenerationResult:
        nonlocal attempts
        attempts += 1
        return PatchGenerationResult(
            proposal=PatchProposal(
                root_cause_explanation=f"Attempt {attempts}",
                unified_diff="",
                file_patches=[
                    FilePatch(
                        file_path="src/calc.py",
                        updated_content=f"# attempt {attempts}\ndef divide(a, b):\n    return 0\n",
                    )
                ],
            ),
            prompt_tokens=80,
            completion_tokens=20,
        )

    async def empty_neighbors(repo: str, query: str) -> list[dict[str, object]]:
        return []

    sandbox = FakeSandboxRunner(
        [
            SandboxResult(passed=False, exit_code=1, stdout="", stderr="AssertionError", duration_ms=100),
            SandboxResult(passed=True, exit_code=0, stdout="1 passed", stderr="", duration_ms=120),
        ]
    )
    deps = NodeDependencies(
        github_client=FakeGitHubClient(),  # type: ignore[arg-type]
        sandbox_runner=sandbox,  # type: ignore[arg-type]
        trace_logger=noop_trace,  # type: ignore[arg-type]
        patch_generator=patch_gen,
        neighbor_search=empty_neighbors,
    )

    final_state = await build_workflow(deps).ainvoke(_base_state())
    assert final_state["final_status"] == IncidentStatus.AWAITING_APPROVAL.value
    assert final_state["retry_count"] == 1
    assert attempts == 2
    assert sandbox.calls == 2
    assert final_state["total_tokens"] == 200


@pytest.mark.asyncio
async def test_workflow_stops_at_max_retries() -> None:
    async def noop_trace(*args: object) -> None:
        return None

    async def patch_gen(state: AgentState) -> PatchGenerationResult:
        return PatchGenerationResult(
            proposal=PatchProposal(
                root_cause_explanation="Retry fix",
                unified_diff="",
                file_patches=[
                    FilePatch(file_path="src/calc.py", updated_content="def divide(a, b):\n    return 1\n")
                ],
            ),
            prompt_tokens=50,
            completion_tokens=10,
        )

    async def empty_neighbors(repo: str, query: str) -> list[dict[str, object]]:
        return []

    sandbox = FakeSandboxRunner(
        [SandboxResult(passed=False, exit_code=1, stdout="", stderr="FAILED", duration_ms=100)]
    )
    deps = NodeDependencies(
        github_client=FakeGitHubClient(),  # type: ignore[arg-type]
        sandbox_runner=sandbox,  # type: ignore[arg-type]
        trace_logger=noop_trace,  # type: ignore[arg-type]
        patch_generator=patch_gen,
        neighbor_search=empty_neighbors,
    )

    final_state = await build_workflow(deps).ainvoke(_base_state())
    assert final_state["final_status"] == IncidentStatus.FAILED_MAX_RETRIES.value
    assert final_state["retry_count"] == 3
    assert sandbox.calls == 3


@pytest.mark.asyncio
async def test_workflow_escalates_on_guardrail_violation() -> None:
    async def noop_trace(*args: object) -> None:
        return None

    async def bad_patch_gen(state: AgentState) -> PatchGenerationResult:
        return PatchGenerationResult(
            proposal=PatchProposal(
                root_cause_explanation="Modify .env",
                unified_diff="--- a/.env\n+++ b/.env\n@@ -1,1 +1,1 @@\n-A=1\n+A=2\n",
                file_patches=[FilePatch(file_path=".env", updated_content="A=2\n")],
            ),
            prompt_tokens=40,
            completion_tokens=10,
        )

    async def empty_neighbors(repo: str, query: str) -> list[dict[str, object]]:
        return []

    sandbox = FakeSandboxRunner([])
    deps = NodeDependencies(
        github_client=FakeGitHubClient(),  # type: ignore[arg-type]
        sandbox_runner=sandbox,  # type: ignore[arg-type]
        trace_logger=noop_trace,  # type: ignore[arg-type]
        patch_generator=bad_patch_gen,
        neighbor_search=empty_neighbors,
    )

    final_state = await build_workflow(deps).ainvoke(_base_state())
    assert final_state["final_status"] == IncidentStatus.ESCALATED_TO_HUMAN.value
    assert final_state["guardrail_passed"] is False
    assert sandbox.calls == 0


def test_parse_arq_redis_settings_tls_and_non_tls() -> None:
    non_tls = parse_arq_redis_settings("redis://default:secret@redis-123.redis-cloud.com:12345")
    assert non_tls.ssl is False
    assert non_tls.host == "redis-123.redis-cloud.com"
    assert non_tls.port == 12345
    assert non_tls.password == "secret"

    tls = parse_arq_redis_settings("rediss://default:secret@upstash.io:6379")
    assert tls.ssl is True
    assert tls.host == "upstash.io"
    assert tls.port == 6379


def test_docker_sandbox_tar_archive_builder() -> None:
    import io
    import tarfile

    archive = _build_tar_archive({"src/app.py": "x = 1\n", "tests/test_app.py": "assert True\n"})
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r") as tar:
        names = sorted(tar.getnames())
    assert names == ["src/app.py", "tests/test_app.py"]

