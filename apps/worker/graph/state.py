"""LangGraph AgentState definition for Patchwork's autonomous healing workflow."""

from typing import TypedDict


class AgentState(TypedDict, total=False):
    """Shared state passed across LangGraph nodes."""

    incident_id: str
    repo_owner: str
    repo_name: str
    base_branch: str
    error_type: str
    error_message: str
    stack_trace: str

    # Triage outputs
    target_file: str
    target_symbol: str
    target_line: int

    # Retrieval outputs
    file_contents: dict[str, str]
    semantic_neighbors: list[dict[str, object]]

    # Patch outputs
    proposed_files: dict[str, str]
    proposed_diff: str
    patch_explanation: str
    guardrail_passed: bool
    guardrail_error: str | None

    # Sandbox verification & loop control
    sandbox_passed: bool
    sandbox_stdout: str
    sandbox_stderr: str
    retry_count: int
    max_retries: int

    # Observability & final status
    total_tokens: int
    final_status: str
