"""ARQ background worker entrypoint executing the LangGraph healing workflow."""

import logging
import uuid

from apps.api.config import get_settings, parse_arq_redis_settings
from apps.api.database import AsyncSessionLocal
from apps.api.models import AgentTrace, Incident, IncidentStatus
from apps.worker.graph.state import AgentState
from apps.worker.graph.workflow import build_workflow
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def process_incident(ctx: dict[str, object], incident_id_str: str) -> dict[str, object]:
    """ARQ task that runs the LangGraph healing pipeline for a queued incident."""
    incident_uuid = uuid.UUID(incident_id_str)
    settings = get_settings()

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Incident).where(Incident.id == incident_uuid))
        incident = result.scalar_one_or_none()
        if incident is None:
            logger.error("Incident '%s' not found in database", incident_id_str)
            return {"status": "NOT_FOUND", "incident_id": incident_id_str}

        incident.status = IncidentStatus.INVESTIGATING
        await session.commit()

        initial_state: AgentState = {
            "incident_id": str(incident.id),
            "repo_owner": incident.repo_owner,
            "repo_name": incident.repo_name,
            "base_branch": incident.base_branch,
            "error_type": incident.error_type,
            "error_message": incident.error_message,
            "stack_trace": incident.stack_trace,
            "file_contents": {},
            "semantic_neighbors": [],
            "retry_count": 0,
            "max_retries": settings.max_agent_retries,
            "total_tokens": incident.total_tokens,
        }

    workflow = build_workflow()
    try:
        final_state: AgentState = await workflow.ainvoke(initial_state)
    except Exception as exc:
        logger.exception("Workflow execution failed for incident %s: %s", incident_id_str, exc)
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Incident).where(Incident.id == incident_uuid))
            incident = result.scalar_one_or_none()
            if incident is not None:
                incident.status = IncidentStatus.ESCALATED_TO_HUMAN
                session.add(
                    AgentTrace(
                        incident_id=incident.id,
                        step_name="worker_error",
                        thought_summary=f"Worker exception escalated to human: {exc}",
                        tool_output=None,
                        tokens_used=0,
                        latency_ms=0,
                    )
                )
                await session.commit()
        return {"incident_id": incident_id_str, "status": IncidentStatus.ESCALATED_TO_HUMAN.value}

    final_status_str = final_state.get("final_status", IncidentStatus.FAILED_MAX_RETRIES.value)
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Incident).where(Incident.id == incident_uuid))
        incident = result.scalar_one_or_none()
        if incident is not None:
            incident.status = IncidentStatus(final_status_str)
            incident.proposed_diff = final_state.get("proposed_diff")
            incident.patch_explanation = final_state.get("patch_explanation")
            incident.retry_count = final_state.get("retry_count", 0)
            incident.total_tokens = final_state.get("total_tokens", 0)
            await session.commit()

    return {
        "incident_id": incident_id_str,
        "status": final_status_str,
        "retry_count": final_state.get("retry_count", 0),
        "total_tokens": final_state.get("total_tokens", 0),
    }


class WorkerSettings:
    """ARQ worker configuration."""

    functions = [process_incident]
    redis_settings = parse_arq_redis_settings(get_settings().redis_url)
    max_jobs = 5
    job_timeout = 300
