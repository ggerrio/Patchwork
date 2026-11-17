"""Pydantic v2 request and response DTOs for the Patchwork API."""

import uuid
from datetime import datetime

from apps.api.models import IncidentStatus
from pydantic import BaseModel, ConfigDict, Field


class IncidentCreateRequest(BaseModel):
    """Payload for ingesting a production error incident."""

    repo_owner: str = Field(..., min_length=1, max_length=255)
    repo_name: str = Field(..., min_length=1, max_length=255)
    base_branch: str = Field(default="main", min_length=1, max_length=100)
    error_type: str = Field(..., min_length=1, max_length=255)
    error_message: str = Field(..., min_length=1)
    stack_trace: str = Field(..., min_length=1)
    file_path: str | None = Field(
        default=None,
        description="Optional file path override; extracted from stack_trace if omitted.",
    )
    line_number: int | None = Field(
        default=None,
        ge=1,
        description="Optional line number override; extracted from stack_trace if omitted.",
    )


class IncidentCreateResponse(BaseModel):
    """Response returned after incident ingestion or deduplication."""

    id: uuid.UUID | None = None
    fingerprint: str
    status: str
    deduplicated: bool
    message: str


class AgentTraceResponse(BaseModel):
    """Serialized observability trace for a single agent step."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    incident_id: uuid.UUID
    step_name: str
    thought_summary: str
    tool_output: str | None
    tokens_used: int
    latency_ms: int
    created_at: datetime


class IncidentResponse(BaseModel):
    """Summary representation of an incident."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fingerprint: str
    repo_owner: str
    repo_name: str
    base_branch: str
    error_type: str
    error_message: str
    stack_trace: str
    status: IncidentStatus
    proposed_diff: str | None
    patch_explanation: str | None
    pr_url: str | None
    retry_count: int
    total_tokens: int
    created_at: datetime
    updated_at: datetime


class IncidentDetailResponse(IncidentResponse):
    """Detailed incident representation including ordered agent traces."""

    traces: list[AgentTraceResponse] = Field(default_factory=list)


class IncidentListResponse(BaseModel):
    """Paginated list of incidents."""

    items: list[IncidentResponse]
    total: int
    limit: int
    offset: int


class IncidentRejectRequest(BaseModel):
    """Payload for rejecting a proposed patch."""

    reason: str = Field(..., min_length=1, max_length=2000)


class ApprovalActionResponse(BaseModel):
    """Response returned after HITL approve or reject transition."""

    id: uuid.UUID
    status: IncidentStatus
    pr_url: str | None = None
    message: str
