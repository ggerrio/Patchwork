"""Human-in-the-Loop (HITL) approval and rejection endpoints."""

import uuid
from typing import Annotated

from apps.api.config import get_settings
from apps.api.database import get_db
from apps.api.schemas import ApprovalActionResponse, IncidentRejectRequest
from apps.api.services.approval_service import (
    ApprovalService,
    IncidentNotFoundError,
    InvalidIncidentStateError,
)
from apps.api.services.github_client import GitHubClient, GitHubClientError
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/v1/incidents", tags=["approvals"])


def get_github_client() -> GitHubClient:
    """Dependency provider for `GitHubClient` (overridable in tests)."""
    settings = get_settings()
    if not settings.github_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GITHUB_TOKEN is not configured on the server.",
        )
    return GitHubClient(token=settings.github_token)


DbSession = Annotated[AsyncSession, Depends(get_db)]
GitHubDep = Annotated[GitHubClient, Depends(get_github_client)]


@router.post("/{incident_id}/approve", response_model=ApprovalActionResponse)
async def approve_incident(
    incident_id: uuid.UUID,
    db: DbSession,
    github_client: GitHubDep,
) -> ApprovalActionResponse:
    """Approve an incident patch, open a GitHub PR, and set status to APPROVED_PR_OPENED."""
    service = ApprovalService(db=db, github_client=github_client)
    try:
        return await service.approve_incident(incident_id)
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidIncidentStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except GitHubClientError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/{incident_id}/reject", response_model=ApprovalActionResponse)
async def reject_incident(
    incident_id: uuid.UUID,
    payload: IncidentRejectRequest,
    db: DbSession,
) -> ApprovalActionResponse:
    """Reject a proposed patch with a reason and set status to REJECTED."""
    service = ApprovalService(db=db)
    try:
        return await service.reject_incident(incident_id, reason=payload.reason)
    except IncidentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidIncidentStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
