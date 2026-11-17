"""Service layer for incident ingestion, deduplication, ARQ enqueueing, and queries."""

import logging
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable

from apps.api.config import get_settings, parse_arq_redis_settings
from apps.api.models import Incident, IncidentStatus
from apps.api.schemas import (
    IncidentCreateRequest,
    IncidentCreateResponse,
    IncidentListResponse,
    IncidentResponse,
)
from apps.api.services.deduplicator import (
    IncidentDeduplicator,
    compute_fingerprint,
    extract_location_from_stack_trace,
)
from arq import create_pool
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

EnqueueFn = Callable[[uuid.UUID], Awaitable[str | None]]


async def get_redis_client() -> AsyncGenerator[Redis, None]:
    """Yield an async Redis client and close it cleanly."""
    settings = get_settings()
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


async def enqueue_incident_job(incident_id: uuid.UUID) -> str | None:
    """Enqueue an ARQ background job to process the given incident."""
    settings = get_settings()
    pool = await create_pool(parse_arq_redis_settings(settings.redis_url))
    try:
        job = await pool.enqueue_job("process_incident", str(incident_id))
        return job.job_id if job is not None else None
    finally:
        await pool.aclose()


class IncidentService:
    """Coordinates incident ingestion, idempotency, persistence, and retrieval."""

    def __init__(
        self,
        db: AsyncSession,
        deduplicator: IncidentDeduplicator | None = None,
        enqueue_fn: EnqueueFn | None = None,
    ) -> None:
        self._db = db
        self._deduplicator = deduplicator
        self._enqueue_fn = enqueue_fn or enqueue_incident_job

    async def ingest_incident(self, payload: IncidentCreateRequest) -> IncidentCreateResponse:
        """Validate, deduplicate, persist, and enqueue a production error incident."""
        if self._deduplicator is None:
            raise RuntimeError("IncidentDeduplicator is required for ingest_incident")

        extracted_file, extracted_line = extract_location_from_stack_trace(payload.stack_trace)
        file_path = payload.file_path or extracted_file
        line_number = payload.line_number if payload.line_number is not None else extracted_line

        fingerprint = compute_fingerprint(payload.error_type, file_path, line_number)
        acquired = await self._deduplicator.acquire_lock(fingerprint)
        if not acquired:
            logger.info(
                "Duplicate incident ignored",
                extra={"fingerprint": fingerprint, "error_type": payload.error_type},
            )
            return IncidentCreateResponse(
                id=None,
                fingerprint=fingerprint,
                status="DUPLICATE_IGNORED",
                deduplicated=True,
                message="Duplicate incident ignored within 3600s idempotency window.",
            )

        incident = Incident(
            fingerprint=fingerprint,
            repo_owner=payload.repo_owner,
            repo_name=payload.repo_name,
            base_branch=payload.base_branch,
            error_type=payload.error_type,
            error_message=payload.error_message,
            stack_trace=payload.stack_trace,
            status=IncidentStatus.QUEUED,
        )

        try:
            self._db.add(incident)
            await self._db.commit()
            await self._db.refresh(incident)
            await self._enqueue_fn(incident.id)
        except Exception as exc:
            logger.exception(
                "Failed to persist or enqueue incident",
                extra={
                    "fingerprint": fingerprint,
                    "incident_id": str(incident.id),
                    "error": str(exc),
                },
            )
            await self._db.rollback()
            await self._deduplicator.release_lock(fingerprint)
            raise

        return IncidentCreateResponse(
            id=incident.id,
            fingerprint=fingerprint,
            status=incident.status.value,
            deduplicated=False,
            message="Incident queued for autonomous triage.",
        )

    async def list_incidents(
        self,
        *,
        status: IncidentStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> IncidentListResponse:
        """Return paginated incidents ordered by newest first."""
        stmt = select(Incident)
        count_stmt = select(func.count()).select_from(Incident)

        if status is not None:
            stmt = stmt.where(Incident.status == status)
            count_stmt = count_stmt.where(Incident.status == status)

        stmt = stmt.order_by(Incident.created_at.desc()).limit(limit).offset(offset)

        result = await self._db.execute(stmt)
        incidents = list(result.scalars().all())

        total_result = await self._db.execute(count_stmt)
        total = int(total_result.scalar_one())

        return IncidentListResponse(
            items=[IncidentResponse.model_validate(item) for item in incidents],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_incident_detail(self, incident_id: uuid.UUID) -> Incident | None:
        """Fetch a single incident with its ordered agent traces."""
        stmt = (
            select(Incident)
            .where(Incident.id == incident_id)
            .options(selectinload(Incident.traces))
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
