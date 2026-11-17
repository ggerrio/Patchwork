"use client";

import { useState } from "react";
import { Check, ExternalLink, Loader2, X } from "lucide-react";

import { approveIncident, rejectIncident } from "@/lib/api";
import type { IncidentStatus } from "@/types/incident";

interface ApprovalControlsProps {
  incidentId: string;
  status: IncidentStatus;
  prUrl: string | null;
  onUpdated: () => Promise<void> | void;
}

export function ApprovalControls({
  incidentId,
  status,
  prUrl,
  onUpdated,
}: ApprovalControlsProps) {
  const [confirmMode, setConfirmMode] = useState<"none" | "approve" | "reject">("none");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (status === "APPROVED_PR_OPENED" && prUrl) {
    return (
      <a
        href={prUrl}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-2 rounded-md border border-[#10B981]/40 bg-[#0F241D] px-4 py-2 text-sm font-medium text-[#10B981] transition hover:bg-[#10B981]/20"
      >
        View Pull Request <ExternalLink className="h-4 w-4" />
      </a>
    );
  }

  const canApprove = status === "AWAITING_APPROVAL";
  const canReject =
    status !== "APPROVED_PR_OPENED" && status !== "REJECTED";

  if (!canApprove && !canReject) {
    return null;
  }

  async function handleApprove() {
    setSubmitting(true);
    setError(null);
    try {
      await approveIncident(incidentId);
      setConfirmMode("none");
      await onUpdated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to approve incident");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReject() {
    if (!reason.trim()) {
      setError("Please provide a rejection reason.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await rejectIncident(incidentId, reason.trim());
      setConfirmMode("none");
      setReason("");
      await onUpdated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reject incident");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2.5">
        {canApprove && confirmMode !== "approve" ? (
          <button
            type="button"
            disabled={submitting}
            onClick={() => {
              setError(null);
              setConfirmMode("approve");
            }}
            className="inline-flex items-center gap-2 rounded-md border border-[#EF4444]/40 bg-[#DC2626] px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-[#B91C1C] disabled:opacity-50"
          >
            <Check className="h-4 w-4" />
            Approve &amp; Open PR
          </button>
        ) : null}

        {canReject && confirmMode !== "reject" ? (
          <button
            type="button"
            disabled={submitting}
            onClick={() => {
              setError(null);
              setConfirmMode("reject");
            }}
            className="inline-flex items-center gap-2 rounded-md border border-[#23262F] bg-[#181B22] px-4 py-2 text-sm font-medium text-[#EF4444] transition hover:border-[#EF4444]/50 hover:bg-[#261216] disabled:opacity-50"
          >
            <X className="h-4 w-4" />
            Reject
          </button>
        ) : null}
      </div>

      {confirmMode === "approve" ? (
        <div className="rounded-md border border-[#23262F] bg-[#0B0C0E] p-4">
          <p className="text-sm text-[#F4F4F5]">
            Open a GitHub Pull Request on a new{" "}
            <code className="font-mono text-[#10B981]">patchwork/fix-*</code> branch?
          </p>
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              disabled={submitting}
              onClick={handleApprove}
              className="inline-flex items-center gap-1.5 rounded-md bg-[#DC2626] px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-[#B91C1C] disabled:opacity-50"
            >
              {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              Confirm &amp; Open PR
            </button>
            <button
              type="button"
              disabled={submitting}
              onClick={() => setConfirmMode("none")}
              className="rounded-md border border-[#23262F] px-3.5 py-1.5 text-xs text-[#9CA3AF] hover:text-[#F4F4F5]"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      {confirmMode === "reject" ? (
        <div className="space-y-3 rounded-md border border-[#EF4444]/40 bg-[#0B0C0E] p-4">
          <label className="block text-xs font-medium text-[#F4F4F5]">
            Reason for rejecting this patch
          </label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
            placeholder="e.g., Should raise ValueError instead of returning 0.0"
            className="w-full rounded-md border border-[#23262F] bg-[#13151A] px-3 py-2 text-sm text-[#F4F4F5] placeholder:text-[#9CA3AF] focus:border-[#EF4444] focus:outline-none"
          />
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={submitting}
              onClick={handleReject}
              className="inline-flex items-center gap-1.5 rounded-md bg-[#EF4444] px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-[#EF4444]/90 disabled:opacity-50"
            >
              {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              Confirm Reject
            </button>
            <button
              type="button"
              disabled={submitting}
              onClick={() => setConfirmMode("none")}
              className="rounded-md border border-[#23262F] px-3.5 py-1.5 text-xs text-[#9CA3AF] hover:text-[#F4F4F5]"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      {error ? (
        <p className="rounded-md border border-[#EF4444]/40 bg-[#261216] px-3.5 py-2.5 text-xs text-[#EF4444]">
          {error}
        </p>
      ) : null}
    </div>
  );
}
