"""LangGraph node implementations: triage, retrieve, patch, and sandbox verification."""

import difflib
import json
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from apps.api.config import get_settings
from apps.api.database import AsyncSessionLocal
from apps.api.models import AgentTrace, CodeChunk, IncidentStatus
from apps.api.services.github_client import GitHubClient
from apps.worker.graph.state import AgentState
from apps.worker.sandbox.docker_runner import DockerSandboxRunner, SandboxResult
from langchain_core.messages import HumanMessage, SystemMessage
from packages.core.guardrails import check_patch
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_TRACEBACK_FRAME_RE = re.compile(r'File\s+"([^"]+)",\s+line\s+(\d+),\s+in\s+([^\s]+)')


class FilePatch(BaseModel):
    """Full replacement content for a single modified file."""

    file_path: str = Field(..., min_length=1)
    updated_content: str


class PatchProposal(BaseModel):
    """Structured LLM output for root-cause diagnosis and patch generation."""

    root_cause_explanation: str = Field(..., min_length=1)
    unified_diff: str = Field(default="")
    file_patches: list[FilePatch] = Field(..., min_length=1, max_length=3)


@dataclass(frozen=True)
class PatchGenerationResult:
    """Normalized return value from an LLM patch call with token accounting."""

    proposal: PatchProposal
    prompt_tokens: int
    completion_tokens: int


TraceLoggerFn = Callable[
    [str, str, str, str | None, int, int, int],
    Awaitable[None],
]
PatchGeneratorFn = Callable[[AgentState], Awaitable[PatchGenerationResult]]
NeighborSearchFn = Callable[[str, str], Awaitable[list[dict[str, object]]]]


@dataclass
class NodeDependencies:
    """Injectable dependencies for LangGraph nodes (production defaults or test doubles)."""

    github_client: GitHubClient | None = None
    sandbox_runner: DockerSandboxRunner | None = None
    trace_logger: TraceLoggerFn | None = None
    patch_generator: PatchGeneratorFn | None = None
    neighbor_search: NeighborSearchFn | None = None


async def default_trace_logger(
    incident_id: str,
    step_name: str,
    thought_summary: str,
    tool_output: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
) -> None:
    """Persist an observability trace row into PostgreSQL `agent_traces`."""
    tokens_used = prompt_tokens + completion_tokens
    summary_with_tokens = (
        f"{thought_summary} "
        f"[prompt_tokens={prompt_tokens}, completion_tokens={completion_tokens}]"
    )
    async with AsyncSessionLocal() as session:
        await _write_trace_row(
            session=session,
            incident_id=uuid.UUID(incident_id),
            step_name=step_name,
            thought_summary=summary_with_tokens,
            tool_output=tool_output,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
        )


async def _write_trace_row(
    *,
    session: AsyncSession,
    incident_id: uuid.UUID,
    step_name: str,
    thought_summary: str,
    tool_output: str | None,
    tokens_used: int,
    latency_ms: int,
) -> None:
    trace = AgentTrace(
        incident_id=incident_id,
        step_name=step_name,
        thought_summary=thought_summary,
        tool_output=tool_output,
        tokens_used=tokens_used,
        latency_ms=latency_ms,
    )
    session.add(trace)
    await session.commit()


def _build_llm_chat_model(*, force_groq: bool = False) -> object:
    settings = get_settings()
    provider = "groq" if force_groq else settings.primary_llm_provider.lower()
    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=settings.groq_api_key,
            temperature=0.0,
            timeout=30.0,
            max_retries=2,
        )

    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.gemini_api_key,
        temperature=0.0,
        timeout=30.0,
        retries=2,
    )


async def default_patch_generator(state: AgentState) -> PatchGenerationResult:
    """Invoke Gemini/Groq with Pydantic structured output to propose a minimal fix."""
    llm = _build_llm_chat_model()
    structured_llm = llm.with_structured_output(PatchProposal, include_raw=True)  # type: ignore[attr-defined]

    files_blob = "\n\n".join(
        f"=== FILE: {path} ===\n{content}"
        for path, content in state.get("file_contents", {}).items()
    )
    neighbors_blob = json.dumps(state.get("semantic_neighbors", []), indent=2)
    stderr_section = ""
    failure_log = "\n".join(
        part
        for part in (
            state.get("sandbox_stderr", "").strip(),
            state.get("sandbox_stdout", "").strip(),
        )
        if part
    )
    if failure_log and state.get("retry_count", 0) > 0:
        stderr_section = (
            f"\nPrevious pytest failure output (fix all failing tests):\n{failure_log}\n"
        )

    system_msg = SystemMessage(
        content=(
            "You are Patchwork, an autonomous senior DevOps & Python engineer. "
            "Diagnose the root cause from the stack trace and source files, then produce "
            "a minimal, surgical fix. Never modify more than 3 files. Never touch .env, "
            "secrets, .github/, or migration files."
        )
    )
    human_msg = HumanMessage(
        content=(
            f"Error Type: {state.get('error_type')}\n"
            f"Error Message: {state.get('error_message')}\n"
            f"Target: {state.get('target_file')}:{state.get('target_line')} "
            f"({state.get('target_symbol')})\n\n"
            f"Stack Trace:\n{state.get('stack_trace')}\n\n"
            f"Source Files:\n{files_blob}\n\n"
            f"Semantic Neighbors:\n{neighbors_blob}\n"
            f"{stderr_section}"
        )
    )

    try:
        response = await structured_llm.ainvoke([system_msg, human_msg])
    except Exception as exc:
        settings = get_settings()
        if settings.groq_api_key and settings.primary_llm_provider.lower() != "groq":
            logger.warning("Primary Gemini LLM failed (%s); falling back to Groq.", exc)
            fallback_llm = _build_llm_chat_model(force_groq=True)
            fallback_structured = fallback_llm.with_structured_output(  # type: ignore[attr-defined]
                PatchProposal, include_raw=True
            )
            response = await fallback_structured.ainvoke([system_msg, human_msg])
        else:
            raise
    parsed: PatchProposal = response["parsed"]
    raw_msg = response.get("raw")
    usage = getattr(raw_msg, "usage_metadata", None) or {}
    prompt_tokens = int(usage.get("input_tokens", 0))
    completion_tokens = int(usage.get("output_tokens", 0))

    return PatchGenerationResult(
        proposal=parsed,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


async def default_neighbor_search(repo_full_name: str, query_text: str) -> list[dict[str, object]]:
    """Query `code_chunks` via pgvector cosine similarity using Gemini embeddings."""
    settings = get_settings()
    if not settings.gemini_api_key:
        return []

    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    embedder = GoogleGenerativeAIEmbeddings(
        model="models/text-embedding-004",
        google_api_key=settings.gemini_api_key,
    )
    query_vec = await embedder.aembed_query(query_text)

    async with AsyncSessionLocal() as session:
        stmt = (
            select(CodeChunk)
            .where(CodeChunk.repo_full_name == repo_full_name)
            .where(CodeChunk.embedding.is_not(None))
            .order_by(CodeChunk.embedding.cosine_distance(query_vec))
            .limit(3)
        )
        result = await session.execute(stmt)
        chunks = result.scalars().all()
        return [
            {
                "file_path": chunk.file_path,
                "symbol_name": chunk.symbol_name,
                "chunk_type": chunk.chunk_type,
                "content": chunk.content,
            }
            for chunk in chunks
        ]


def _synthesize_unified_diff(
    original_files: dict[str, str],
    file_patches: list[FilePatch],
) -> str:
    """Generate a valid unified diff from original and updated file contents."""
    diffs: list[str] = []
    for patch in file_patches:
        before = original_files.get(patch.file_path, "").splitlines(keepends=True)
        after = patch.updated_content.splitlines(keepends=True)
        diff_lines = list(
            difflib.unified_diff(
                before,
                after,
                fromfile=f"a/{patch.file_path}",
                tofile=f"b/{patch.file_path}",
            )
        )
        if diff_lines:
            diffs.append("".join(diff_lines))
    return "\n".join(diffs)


async def _log_step(
    deps: NodeDependencies,
    *,
    incident_id: str,
    step_name: str,
    thought_summary: str,
    tool_output: str | None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: int = 0,
) -> None:
    if not incident_id:
        return
    logger_fn = deps.trace_logger or default_trace_logger
    try:
        await logger_fn(
            incident_id,
            step_name,
            thought_summary,
            tool_output,
            prompt_tokens,
            completion_tokens,
            latency_ms,
        )
    except Exception as exc:
        logger.exception("Failed to record agent trace for %s: %s", step_name, exc)


async def triage_node(state: AgentState, deps: NodeDependencies) -> AgentState:
    """Parse stack trace to identify target file, line number, and symbol."""
    started = time.perf_counter()
    stack_trace = state.get("stack_trace", "")
    matches = _TRACEBACK_FRAME_RE.findall(stack_trace)

    if matches:
        target_file, line_str, target_symbol = matches[-1]
        target_line = int(line_str)
    else:
        target_file = state.get("target_file", "unknown")
        target_line = state.get("target_line", 0)
        target_symbol = state.get("target_symbol", "<module>")

    latency_ms = int((time.perf_counter() - started) * 1000)
    await _log_step(
        deps,
        incident_id=state.get("incident_id", ""),
        step_name="triage_node",
        thought_summary=f"Identified fault site at {target_file}:{target_line} in {target_symbol}",
        tool_output=json.dumps(
            {"file": target_file, "line": target_line, "symbol": target_symbol}
        ),
        latency_ms=latency_ms,
    )
    return {
        "target_file": target_file.strip(),
        "target_line": target_line,
        "target_symbol": target_symbol.strip(),
    }


async def retrieve_node(state: AgentState, deps: NodeDependencies) -> AgentState:
    """Fetch exact target file from GitHub and semantic neighbors from pgvector."""
    started = time.perf_counter()
    settings = get_settings()
    file_contents: dict[str, str] = dict(state.get("file_contents", {}))
    target_file = state.get("target_file", "")

    github = deps.github_client
    if github is None and settings.github_token:
        github = GitHubClient(token=settings.github_token)

    if github is not None and target_file and target_file != "unknown":
        candidate_paths = [target_file]
        if "/" in target_file:
            parent_dir, filename = target_file.rsplit("/", 1)
            candidate_paths.append(f"{parent_dir}/test_{filename}")
            candidate_paths.append(f"tests/test_{filename}")
        else:
            candidate_paths.append(f"test_{target_file}")
            candidate_paths.append(f"tests/test_{target_file}")

        for path in candidate_paths:
            if path in file_contents:
                continue
            try:
                content = await github.fetch_file_contents(
                    state["repo_owner"],
                    state["repo_name"],
                    path,
                    ref=state.get("base_branch", "main"),
                )
                file_contents[path] = content
            except Exception as exc:
                logger.debug("Optional/target file '%s' not fetched from GitHub: %s", path, exc)

    neighbors: list[dict[str, object]] = []
    search_fn = deps.neighbor_search or default_neighbor_search
    repo_full_name = f"{state.get('repo_owner', '')}/{state.get('repo_name', '')}"
    query_text = f"{state.get('error_type', '')}: {state.get('error_message', '')}"
    try:
        neighbors = await search_fn(repo_full_name, query_text)
    except Exception as exc:
        logger.warning("pgvector semantic neighbor search failed: %s", exc)

    latency_ms = int((time.perf_counter() - started) * 1000)
    await _log_step(
        deps,
        incident_id=state.get("incident_id", ""),
        step_name="retrieve_node",
        thought_summary=(
            f"Retrieved {len(file_contents)} file(s) and {len(neighbors)} semantic neighbor(s)"
        ),
        tool_output=json.dumps({"files": list(file_contents.keys()), "neighbors": len(neighbors)}),
        latency_ms=latency_ms,
    )
    return {
        "file_contents": file_contents,
        "semantic_neighbors": neighbors,
    }


async def patch_node(state: AgentState, deps: NodeDependencies) -> AgentState:
    """Generate a structured patch via LLM and validate it against security guardrails."""
    started = time.perf_counter()
    generator = deps.patch_generator or default_patch_generator
    gen_result = await generator(state)
    proposal = gen_result.proposal

    proposed_files = {fp.file_path: fp.updated_content for fp in proposal.file_patches}
    diff_text = proposal.unified_diff.strip()
    if not diff_text:
        diff_text = _synthesize_unified_diff(state.get("file_contents", {}), proposal.file_patches)

    guardrail_result = check_patch(list(proposed_files.keys()), diff_text)
    if not guardrail_result.passed and proposal.unified_diff.strip():
        # Retry diff synthesis from exact file contents if LLM diff header was malformed
        synthesized = _synthesize_unified_diff(
            state.get("file_contents", {}), proposal.file_patches
        )
        if synthesized:
            retry_check = check_patch(list(proposed_files.keys()), synthesized)
            if retry_check.passed:
                diff_text = synthesized
                guardrail_result = retry_check

    latency_ms = int((time.perf_counter() - started) * 1000)
    total_tokens = (
        state.get("total_tokens", 0) + gen_result.prompt_tokens + gen_result.completion_tokens
    )

    await _log_step(
        deps,
        incident_id=state.get("incident_id", ""),
        step_name="patch_node",
        thought_summary=proposal.root_cause_explanation,
        tool_output=json.dumps(
            {
                "modified_files": list(proposed_files.keys()),
                "guardrail_passed": guardrail_result.passed,
                "guardrail_error": guardrail_result.reason,
            }
        ),
        prompt_tokens=gen_result.prompt_tokens,
        completion_tokens=gen_result.completion_tokens,
        latency_ms=latency_ms,
    )

    if not guardrail_result.passed:
        return {
            "proposed_files": proposed_files,
            "proposed_diff": diff_text,
            "patch_explanation": proposal.root_cause_explanation,
            "guardrail_passed": False,
            "guardrail_error": guardrail_result.reason,
            "total_tokens": total_tokens,
            "final_status": IncidentStatus.ESCALATED_TO_HUMAN.value,
        }

    return {
        "proposed_files": proposed_files,
        "proposed_diff": diff_text,
        "patch_explanation": proposal.root_cause_explanation,
        "guardrail_passed": True,
        "guardrail_error": None,
        "total_tokens": total_tokens,
    }


async def sandbox_node(state: AgentState, deps: NodeDependencies) -> AgentState:
    """Apply proposed patch in an isolated Docker sandbox and run `pytest`."""
    started = time.perf_counter()
    settings = get_settings()
    runner = deps.sandbox_runner
    if runner is None:
        runner = DockerSandboxRunner(image=settings.sandbox_image)

    merged_files = {
        **state.get("file_contents", {}),
        **state.get("proposed_files", {}),
    }

    result: SandboxResult = await runner.run_pytest(merged_files)
    latency_ms = int((time.perf_counter() - started) * 1000)

    current_retries = state.get("retry_count", 0)
    max_retries = state.get("max_retries", settings.max_agent_retries)

    if result.passed:
        final_status = IncidentStatus.AWAITING_APPROVAL.value
        next_retries = current_retries
    else:
        next_retries = current_retries + 1
        final_status = (
            IncidentStatus.FAILED_MAX_RETRIES.value
            if next_retries >= max_retries
            else IncidentStatus.PATCHING.value
        )

    await _log_step(
        deps,
        incident_id=state.get("incident_id", ""),
        step_name="sandbox_node",
        thought_summary=(
            f"Sandbox pytest {'PASSED' if result.passed else 'FAILED'} "
            f"(exit_code={result.exit_code}, retry={next_retries}/{max_retries})"
        ),
        tool_output=(result.stderr or result.stdout)[:2000],
        latency_ms=latency_ms,
    )

    return {
        "sandbox_passed": result.passed,
        "sandbox_stdout": result.stdout,
        "sandbox_stderr": result.stderr,
        "retry_count": next_retries,
        "final_status": final_status,
    }
