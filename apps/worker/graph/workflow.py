"""Compiled LangGraph cyclic StateGraph for autonomous incident healing."""

from functools import partial

from apps.worker.graph.nodes import (
    NodeDependencies,
    patch_node,
    retrieve_node,
    sandbox_node,
    triage_node,
)
from apps.worker.graph.state import AgentState
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph


def _route_after_patch(state: AgentState) -> str:
    """Halt immediately if security guardrails were violated."""
    if not state.get("guardrail_passed", False):
        return END
    return "sandbox_node"


def _route_after_sandbox(state: AgentState) -> str:
    """End on pass or max_retries exhausted; otherwise loop back to patch_node."""
    if state.get("sandbox_passed", False):
        return END
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)
    if retry_count >= max_retries:
        return END
    return "patch_node"


def build_workflow(deps: NodeDependencies | None = None) -> CompiledStateGraph:
    """Build and compile the bounded cyclic LangGraph workflow."""
    resolved_deps = deps or NodeDependencies()

    graph = StateGraph(AgentState)
    graph.add_node("triage_node", partial(triage_node, deps=resolved_deps))
    graph.add_node("retrieve_node", partial(retrieve_node, deps=resolved_deps))
    graph.add_node("patch_node", partial(patch_node, deps=resolved_deps))
    graph.add_node("sandbox_node", partial(sandbox_node, deps=resolved_deps))

    graph.add_edge(START, "triage_node")
    graph.add_edge("triage_node", "retrieve_node")
    graph.add_edge("retrieve_node", "patch_node")

    graph.add_conditional_edges(
        "patch_node",
        _route_after_patch,
        {
            "sandbox_node": "sandbox_node",
            END: END,
        },
    )
    graph.add_conditional_edges(
        "sandbox_node",
        _route_after_sandbox,
        {
            "patch_node": "patch_node",
            END: END,
        },
    )

    return graph.compile()
