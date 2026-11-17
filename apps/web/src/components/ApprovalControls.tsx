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
        className="inline-flex items-center gap-2 rounded-lg border border-emerald-700 bg-emerald-950/70 px-4 py-2 text-sm font-medium text-emerald-200 hover:bg-emerald-900/70"
      >
        View Opened Pull Request <ExternalLink className="h-4 w-4" />
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
      <div className="flex flex-wrap items-center gap-3">
        {canApprove && confirmMode !== "approve" ? (
          <button
            type="button"
            disabled={submitting}
            onClick={() => {
              setError(null);
              setConfirmMode("approve");
            }}
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:opacity-50"
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
            className="inline-flex items-center gap-2 rounded-lg border border-rose-800 bg-rose-950/60 px-4 py-2 text-sm font-semibold text-rose-200 transition hover:bg-rose-900/70 disabled:opacity-50"
          >
            <X className="h-4 w-4" />
            Reject Patch
          </button>
        ) : null}
      </div>

      {confirmMode === "approve" ? (
        <div className="rounded-xl border border-emerald-800 bg-emerald-950/30 p-4">
          <p className="text-sm text-emerald-100">
            Confirm opening a GitHub Pull Request on a new{" "}
            <code className="font-mono text-emerald-300">patchwork/fix-*</code> branch?
          </p>
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              disabled={submitting}
              onClick={handleApprove}
              className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
            >
              {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              Confirm &amp; Open PR
            </button>
            <button
              type="button"
              disabled={submitting}
              onClick={() => setConfirmMode("none")}
              className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      {confirmMode === "reject" ? (
        <div className="rounded-xl border border-rose-800 bg-rose-950/30 p-4 space-y-3">
          <label className="block text-xs font-medium text-rose-200">
            Rejection reason (recorded in agent traces)
          </label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
            placeholder="e.g., Should raise ValueError instead of returning 0.0"
            className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-rose-500 focus:outline-none"
          />
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={submitting}
              onClick={handleReject}
              className="inline-flex items-center gap-1.5 rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-500 disabled:opacity-50"
            >
              {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              Confirm Reject
            </button>
            <button
              type="button"
              disabled={submitting}
              onClick={() => setConfirmMode("none")}
              className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      {error ? (
        <p className="rounded-lg border border-red-800 bg-red-950/60 px-3 py-2 text-xs text-red-200">
          {error}
        </p>
      ) : null}
    </div>
  );
}

