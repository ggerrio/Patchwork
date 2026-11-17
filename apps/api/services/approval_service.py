"""Service layer for Human-in-the-Loop (HITL) approval and rejection transitions."""

import logging
import re
import uuid
from dataclasses import dataclass

from apps.api.models import AgentTrace, Incident, IncidentStatus
from apps.api.schemas import ApprovalActionResponse
from apps.api.services.github_client import GitHubClient
from packages.core.guardrails import validate_patch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class IncidentNotFoundError(LookupError):
    """Raised when the target incident does not exist."""


class InvalidIncidentStateError(ValueError):
    """Raised when an incident is not in a valid state for the requested HITL action."""


@dataclass(frozen=True)
class _FileDiffSection:
    file_path: str
    hunk_lines: list[str]


def _strip_diff_prefix(raw: str) -> str:
    path = raw.split("\t", 1)[0].strip()
    if path.startswith(("a/", "b/")):
        return path[2:]
    return path


def _split_diff_sections(diff_text: str) -> list[_FileDiffSection]:
    """Split a unified diff into per-file sections."""
    lines = diff_text.splitlines(keepends=True)
    sections: list[_FileDiffSection] = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("--- "):
            new_path = _strip_diff_prefix(lines[i + 1][4:])
            i += 2
            hunk_lines: list[str] = []
            while i < len(lines) and not lines[i].startswith(("--- ", "diff --git ")):
                hunk_lines.append(lines[i])
                i += 1
            sections.append(_FileDiffSection(file_path=new_path, hunk_lines=hunk_lines))
        else:
            i += 1
    return sections


def apply_unified_diff(original_content: str, hunk_lines: list[str]) -> str:
    """Apply unified diff hunks for a single file onto `original_content`."""
    orig_lines = original_content.splitlines(keepends=True)
    result: list[str] = []
    orig_idx = 0
    i = 0

    while i < len(hunk_lines):
        header = hunk_lines[i].rstrip("\r\n")
        match = _HUNK_RE.match(header)
        if not match:
            i += 1
            continue

        old_start = max(int(match.group(1)) - 1, 0)
        while orig_idx < old_start and orig_idx < len(orig_lines):
            result.append(orig_lines[orig_idx])
            orig_idx += 1

        i += 1
        while i < len(hunk_lines) and not hunk_lines[i].startswith("@@ "):
            line = hunk_lines[i]
            if line.startswith(" "):
                if orig_idx < len(orig_lines):
                    result.append(orig_lines[orig_idx])
                    orig_idx += 1
                else:
                    result.append(line[1:])
            elif line.startswith("-"):
                orig_idx += 1
            elif line.startswith("+"):
                result.append(line[1:])
            i += 1

    while orig_idx < len(orig_lines):
        result.append(orig_lines[orig_idx])
        orig_idx += 1

    return "".join(result)


class ApprovalService:
    """Coordinates HITL approve (branch + commit + PR) and reject workflows."""

    def __init__(self, db: AsyncSession, github_client: GitHubClient | None = None) -> None:
        self._db = db
        self._github = github_client

    async def _get_incident_or_raise(self, incident_id: uuid.UUID) -> Incident:
        result = await self._db.execute(select(Incident).where(Incident.id == incident_id))
        incident = result.scalar_one_or_none()
        if incident is None:
            raise IncidentNotFoundError(f"Incident '{incident_id}' not found")
        return incident

    async def approve_incident(self, incident_id: uuid.UUID) -> ApprovalActionResponse:
        """Open a GitHub PR for an approved incident and mark it `APPROVED_PR_OPENED`."""
        if self._github is None:
            raise RuntimeError("GitHubClient is required for approve_incident")

        incident = await self._get_incident_or_raise(incident_id)
        if incident.status != IncidentStatus.AWAITING_APPROVAL:
            raise InvalidIncidentStateError(
                f"Incident '{incident_id}' cannot be approved from status '{incident.status.value}'"
            )
        if not incident.proposed_diff:
            raise InvalidIncidentStateError(
                f"Incident '{incident_id}' has no proposed_diff to apply"
            )

        sections = _split_diff_sections(incident.proposed_diff)
        target_files = [sec.file_path for sec in sections]
        validate_patch(target_files, incident.proposed_diff)

        patched_files: dict[str, str] = {}
        for section in sections:
            original = await self._github.fetch_file_contents(
                incident.repo_owner,
                incident.repo_name,
                section.file_path,
                ref=incident.base_branch,
            )
            patched_files[section.file_path] = apply_unified_diff(original, section.hunk_lines)

        branch_name = f"patchwork/fix-{incident.id}"
        await self._github.create_branch(
            incident.repo_owner,
            incident.repo_name,
            branch_name=branch_name,
            base_branch=incident.base_branch,
        )

        commit_message = f"fix({incident.error_type}): autonomous patch for {incident.id}"
        await self._github.commit_patched_files(
            incident.repo_owner,
            incident.repo_name,
            branch_name=branch_name,
            files=patched_files,
            commit_message=commit_message,
        )

        pr_body = (
            f"## Patchwork Autonomous Fix\n\n"
            f"- **Incident ID:** `{incident.id}`\n"
            f"- **Error:** `{incident.error_type}: {incident.error_message}`\n\n"
            f"### Root Cause & Explanation\n"
            f"{incident.patch_explanation or 'Verified in isolated E2B sandbox.'}\n"
        )
        pr_url = await self._github.open_pull_request(
            incident.repo_owner,
            incident.repo_name,
            head_branch=branch_name,
            base_branch=incident.base_branch,
            title=f"[Patchwork] Fix {incident.error_type} ({str(incident.id)[:8]})",
            body=pr_body,
        )

        incident.pr_url = pr_url
        incident.status = IncidentStatus.APPROVED_PR_OPENED
        self._db.add(
            AgentTrace(
                incident_id=incident.id,
                step_name="hitl_approved",
                thought_summary="Human approved patch; opened GitHub Pull Request.",
                tool_output=pr_url,
                tokens_used=0,
                latency_ms=0,
            )
        )
        await self._db.commit()
        await self._db.refresh(incident)

        return ApprovalActionResponse(
            id=incident.id,
            status=incident.status,
            pr_url=pr_url,
            message="Pull Request opened and incident marked as APPROVED_PR_OPENED.",
        )

    async def reject_incident(
        self,
        incident_id: uuid.UUID,
        reason: str,
    ) -> ApprovalActionResponse:
        """Reject a proposed patch with a human-provided reason."""
        incident = await self._get_incident_or_raise(incident_id)
        if incident.status in {IncidentStatus.APPROVED_PR_OPENED, IncidentStatus.REJECTED}:
            raise InvalidIncidentStateError(
                f"Incident '{incident_id}' cannot be rejected from status '{incident.status.value}'"
            )

        incident.status = IncidentStatus.REJECTED
        self._db.add(
            AgentTrace(
                incident_id=incident.id,
                step_name="hitl_rejected",
                thought_summary=f"Rejected by human reviewer: {reason}",
                tool_output=None,
                tokens_used=0,
                latency_ms=0,
            )
        )
        await self._db.commit()
        await self._db.refresh(incident)

        return ApprovalActionResponse(
            id=incident.id,
            status=incident.status,
            pr_url=incident.pr_url,
            message="Incident marked as REJECTED.",
        )
