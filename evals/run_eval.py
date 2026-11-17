"""Automated benchmark runner for Patchwork across 15 synthetic Python bug cases."""

import argparse
import asyncio
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from apps.api.models import IncidentStatus
from apps.worker.graph.nodes import (
    FilePatch,
    NodeDependencies,
    PatchGenerationResult,
    PatchProposal,
)
from apps.worker.graph.state import AgentState
from apps.worker.graph.workflow import build_workflow
from apps.worker.sandbox.docker_runner import DockerSandboxRunner, SandboxResult
from evals.dataset import EVAL_CASES, EvalCase


@dataclass(frozen=True)
class CaseResult:
    """Benchmark outcome for a single evaluation case."""

    case_id: str
    title: str
    passed: bool
    final_status: str
    retry_count: int
    total_tokens: int
    latency_ms: int


class LocalPytestSandboxRunner:
    """Runs real `pytest` inside an ephemeral temporary directory for offline evals."""

    async def run_pytest(
        self,
        files: dict[str, str],
        test_command: str = "pytest -q",
        timeout_seconds: int = 30,
    ) -> SandboxResult:
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="patchwork_eval_") as tmpdir:
            root = Path(tmpdir)
            for rel_path, content in files.items():
                target = root / rel_path.lstrip("/")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")

            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pytest",
                "-q",
                cwd=str(root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_seconds
            )
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return SandboxResult(
                passed=proc.returncode == 0,
                exit_code=proc.returncode or 0,
                stdout=stdout_b.decode("utf-8", errors="replace"),
                stderr=stderr_b.decode("utf-8", errors="replace"),
                duration_ms=elapsed_ms,
            )


class _InMemoryGitHubStub:
    """Provides case files to `retrieve_node` without external GitHub calls."""

    def __init__(self, files: dict[str, str]) -> None:
        self._files = files

    async def fetch_file_contents(
        self, repo_owner: str, repo_name: str, file_path: str, ref: str = "main"
    ) -> str:
        return self._files[file_path]


async def _noop_trace_logger(*args: object) -> None:
    return None


async def _empty_neighbors(repo: str, query: str) -> list[dict[str, object]]:
    return []


async def run_single_case(case: EvalCase, *, mode: str = "local") -> CaseResult:
    """Execute the LangGraph pipeline for one `EvalCase`."""
    started = time.perf_counter()

    if mode == "live":
        from apps.api.config import get_settings

        settings = get_settings()
        deps = NodeDependencies(
            github_client=_InMemoryGitHubStub(case.files),  # type: ignore[arg-type]
            sandbox_runner=DockerSandboxRunner(image=settings.sandbox_image),
            trace_logger=_noop_trace_logger,
            neighbor_search=_empty_neighbors,
        )
    else:
        async def oracle_patch_generator(state: AgentState) -> PatchGenerationResult:
            patches = [
                FilePatch(file_path=path, updated_content=content)
                for path, content in case.reference_fix.items()
            ]
            return PatchGenerationResult(
                proposal=PatchProposal(
                    root_cause_explanation=f"Reference fix for {case.title}",
                    unified_diff="",
                    file_patches=patches,
                ),
                prompt_tokens=180,
                completion_tokens=70,
            )

        deps = NodeDependencies(
            github_client=_InMemoryGitHubStub(case.files),  # type: ignore[arg-type]
            sandbox_runner=LocalPytestSandboxRunner(),  # type: ignore[arg-type]
            trace_logger=_noop_trace_logger,
            patch_generator=oracle_patch_generator,
            neighbor_search=_empty_neighbors,
        )

    initial_state: AgentState = {
        "incident_id": "",
        "repo_owner": "eval",
        "repo_name": case.case_id,
        "base_branch": "main",
        "error_type": case.error_type,
        "error_message": case.error_message,
        "stack_trace": case.stack_trace,
        "file_contents": dict(case.files),
        "semantic_neighbors": [],
        "retry_count": 0,
        "max_retries": 3,
        "total_tokens": 0,
    }

    final_state = await build_workflow(deps).ainvoke(initial_state)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    final_status = final_state.get("final_status", IncidentStatus.FAILED_MAX_RETRIES.value)

    return CaseResult(
        case_id=case.case_id,
        title=case.title,
        passed=final_status == IncidentStatus.AWAITING_APPROVAL.value,
        final_status=final_status,
        retry_count=int(final_state.get("retry_count", 0)),
        total_tokens=int(final_state.get("total_tokens", 0)),
        latency_ms=elapsed_ms,
    )


def format_markdown_scorecard(results: list[CaseResult]) -> str:
    """Render a Markdown benchmark scorecard from evaluation results."""
    total = len(results)
    passed_count = sum(1 for r in results if r.passed)
    resolution_rate = (passed_count / total * 100.0) if total else 0.0
    avg_latency = (sum(r.latency_ms for r in results) / total) if total else 0.0
    avg_tokens = (sum(r.total_tokens for r in results) / total) if total else 0.0
    retry_dist = Counter(r.retry_count for r in results)

    lines = [
        "# Patchwork Benchmark Scorecard",
        "",
        "## Summary Metrics",
        f"- **Cases Evaluated:** {total}",
        f"- **Resolution Rate %:** {resolution_rate:.1f}% ({passed_count}/{total})",
        f"- **Avg Latency:** {avg_latency:.1f} ms",
        f"- **Avg Tokens:** {avg_tokens:.1f}",
        (
            "- **Retry Distribution:** "
            + ", ".join(f"{k} retries: {retry_dist[k]}" for k in sorted(retry_dist))
        ),
        "",
        "## Per-Case Results",
        "| Case ID | Status | Retries | Tokens | Latency (ms) |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for r in results:
        badge = "PASS" if r.passed else f"FAIL ({r.final_status})"
        lines.append(
            f"| `{r.case_id}` | {badge} | {r.retry_count} | {r.total_tokens} | {r.latency_ms} |"
        )
    return "\n".join(lines) + "\n"


async def run_benchmark(*, mode: str = "local") -> list[CaseResult]:
    """Run all 15 benchmark cases sequentially and return results."""
    results: list[CaseResult] = []
    for case in EVAL_CASES:
        results.append(await run_single_case(case, mode=mode))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Patchwork 15-case benchmark suite.")
    parser.add_argument(
        "--mode",
        choices=["local", "live"],
        default="local",
        help="Use 'local' (tempdir pytest + reference oracle) or 'live' (E2B + LLM API).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the Markdown scorecard.",
    )
    args = parser.parse_args()

    results = asyncio.run(run_benchmark(mode=args.mode))
    scorecard = format_markdown_scorecard(results)
    print(scorecard)
    if args.output is not None:
        args.output.write_text(scorecard, encoding="utf-8")


if __name__ == "__main__":
    main()
