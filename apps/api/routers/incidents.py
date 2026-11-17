"""Incident ingestion and query endpoints."""

import uuid
from typing import Annotated

from apps.api.database import get_db
from apps.api.models import IncidentStatus
from apps.api.schemas import (
    IncidentCreateRequest,
    IncidentCreateResponse,
    IncidentDetailResponse,
    IncidentListResponse,
)
from apps.api.services.deduplicator import IncidentDeduplicator
from apps.api.services.incident_service import (
    EnqueueFn,
    IncidentService,
    enqueue_incident_job,
    get_redis_client,
)
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/v1/incidents", tags=["incidents"])


def get_enqueue_fn() -> EnqueueFn:
    """Dependency provider for ARQ job enqueueing (overridable in tests)."""
    return enqueue_incident_job


DbSession = Annotated[AsyncSession, Depends(get_db)]
RedisDep = Annotated[Redis, Depends(get_redis_client)]
EnqueueDep = Annotated[EnqueueFn, Depends(get_enqueue_fn)]


@router.post("", response_model=IncidentCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_incident(
    payload: IncidentCreateRequest,
    response: Response,
    db: DbSession,
    redis_client: RedisDep,
    enqueue_fn: EnqueueDep,
) -> IncidentCreateResponse:
    """Ingest a production error incident, enforce Redis idempotency, and enqueue ARQ job."""
    service = IncidentService(
        db=db,
        deduplicator=IncidentDeduplicator(redis_client),
        enqueue_fn=enqueue_fn,
    )
    result = await service.ingest_incident(payload)
    if result.deduplicated:
        response.status_code = status.HTTP_200_OK
    return result


@router.get("", response_model=IncidentListResponse)
async def list_incidents(
    db: DbSession,
    status_filter: Annotated[IncidentStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> IncidentListResponse:
    """List ingested incidents with optional status filter and pagination."""
    service = IncidentService(db=db)
    return await service.list_incidents(status=status_filter, limit=limit, offset=offset)


@router.get("/{incident_id}", response_model=IncidentDetailResponse)
async def get_incident(
    incident_id: uuid.UUID,
    db: DbSession,
) -> IncidentDetailResponse:
    """Return full details for a single incident including ordered agent traces."""
    service = IncidentService(db=db)
    incident = await service.get_incident_detail(incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident '{incident_id}' not found",
        )
    return IncidentDetailResponse.model_validate(incident)
