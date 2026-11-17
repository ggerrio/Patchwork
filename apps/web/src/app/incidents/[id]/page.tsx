"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Coins, GitBranch, RotateCcw } from "lucide-react";

import { ApprovalControls } from "@/components/ApprovalControls";
import { DiffViewer } from "@/components/DiffViewer";
import { StatusBadge } from "@/components/StatusBadge";
import { TraceTimeline } from "@/components/TraceTimeline";
import { getIncident } from "@/lib/api";
import type { IncidentDetail } from "@/types/incident";

export default function IncidentDetailPage() {
  const params = useParams<{ id: string }>();
  const incidentId = params.id;

  const [incident, setIncident] = useState<IncidentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDetail = useCallback(async () => {
    if (!incidentId) return;
    try {
      const data = await getIncident(incidentId);
      setIncident(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load incident");
    } finally {
      setLoading(false);
    }
  }, [incidentId]);

  useEffect(() => {
    void loadDetail();
  }, [loadDetail]);

  if (loading) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-10 text-center text-sm text-slate-400">
        Loading incident details...
      </div>
    );
  }

  if (error || !incident) {
    return (
      <div className="space-y-4">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-sm text-sky-400 hover:underline"
        >
          <ArrowLeft className="h-4 w-4" /> Back to Incident Queue
        </Link>
        <div className="rounded-xl border border-red-800 bg-red-950/50 p-4 text-sm text-red-200">
          {error ?? "Incident not found"}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="space-y-4">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-400 hover:text-sky-400"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Incident Queue
        </Link>

        <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="space-y-1.5">
              <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
                <span className="inline-flex items-center gap-1 font-mono text-slate-200">
                  <GitBranch className="h-3.5 w-3.5 text-slate-500" />
                  {incident.repo_owner}/{incident.repo_name} ({incident.base_branch})
                </span>
                <span>•</span>
                <span className="font-mono text-slate-500">{incident.id}</span>
              </div>
              <h1 className="text-xl font-bold text-slate-100">
                {incident.error_type}:{" "}
                <span className="font-normal text-slate-300">
                  {incident.error_message}
                </span>
              </h1>
            </div>

            <StatusBadge status={incident.status} />
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-6 text-xs text-slate-400">
            <span className="inline-flex items-center gap-1.5">
              <RotateCcw className="h-3.5 w-3.5 text-slate-500" />
              Retries: <strong className="text-slate-200">{incident.retry_count}/3</strong>
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Coins className="h-3.5 w-3.5 text-slate-500" />
              Total Tokens:{" "}
              <strong className="text-slate-200">
                {incident.total_tokens.toLocaleString()}
              </strong>
            </span>
            <span className="font-mono text-slate-500">
              Fingerprint: {incident.fingerprint.slice(0, 16)}...
            </span>
          </div>

          {incident.patch_explanation ? (
            <div className="mt-5 rounded-lg border border-slate-800 bg-slate-950/70 p-4">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                AI Root-Cause Diagnosis
              </h2>
              <p className="mt-1.5 text-sm text-slate-200">
                {incident.patch_explanation}
              </p>
            </div>
          ) : null}

          <div className="mt-5">
            <ApprovalControls
              incidentId={incident.id}
              status={incident.status}
              prUrl={incident.pr_url}
              onUpdated={loadDetail}
            />
          </div>
        </div>
      </div>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-slate-100">
          Proposed Code Diff
        </h2>
        <DiffViewer proposedDiff={incident.proposed_diff} />
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-slate-100">
          Agent Trace Timeline
        </h2>
        <TraceTimeline traces={incident.traces} />
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-slate-100">
          Original Stack Trace
        </h2>
        <pre className="overflow-auto rounded-xl border border-slate-800 bg-slate-950 p-4 font-mono text-xs text-slate-300">
          {incident.stack_trace}
        </pre>
      </section>
    </div>
  );
}

