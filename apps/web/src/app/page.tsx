"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Terminal } from "lucide-react";

import { IncidentCard } from "@/components/IncidentCard";
import { listIncidents } from "@/lib/api";
import type { Incident, IncidentStatus } from "@/types/incident";

const STATUS_FILTERS: Array<{ label: string; value: IncidentStatus | "ALL" }> = [
  { label: "All", value: "ALL" },
  { label: "Awaiting Approval", value: "AWAITING_APPROVAL" },
  { label: "Investigating / Patching", value: "INVESTIGATING" },
  { label: "PR Opened", value: "APPROVED_PR_OPENED" },
  { label: "Escalated", value: "ESCALATED_TO_HUMAN" },
  { label: "Failed", value: "FAILED_MAX_RETRIES" },
  { label: "Rejected", value: "REJECTED" },
];

export default function IncidentQueuePage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState<IncidentStatus | "ALL">("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchQueue = useCallback(async () => {
    try {
      const data = await listIncidents({ status: statusFilter, limit: 50 });
      setIncidents(data.items);
      setTotal(data.total);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load incidents");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    setLoading(true);
    void fetchQueue();
    const timer = setInterval(() => {
      void fetchQueue();
    }, 5000);
    return () => clearInterval(timer);
  }, [fetchQueue]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-100">
            Incident Queue
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Live autonomous triage, E2B verification, and HITL approval queue ({total}{" "}
            total).
          </p>
        </div>

        <button
          type="button"
          onClick={() => void fetchQueue()}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-900 px-3.5 py-2 text-xs font-medium text-slate-200 hover:bg-slate-800"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      <div className="flex flex-wrap gap-2">
        {STATUS_FILTERS.map((item) => {
          const active = statusFilter === item.value;
          return (
            <button
              key={item.value}
              type="button"
              onClick={() => setStatusFilter(item.value)}
              className={`rounded-lg border px-3 py-1.5 text-xs font-medium transition ${
                active
                  ? "border-sky-500/60 bg-sky-500/15 text-sky-300"
                  : "border-slate-800 bg-slate-900/60 text-slate-400 hover:border-slate-700 hover:text-slate-200"
              }`}
            >
              {item.label}
            </button>
          );
        })}
      </div>

      {error ? (
        <div className="rounded-xl border border-red-800 bg-red-950/50 p-4 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      {loading && incidents.length === 0 ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-10 text-center text-sm text-slate-400">
          Loading incident queue...
        </div>
      ) : incidents.length === 0 ? (
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-10 text-center">
          <Terminal className="mx-auto h-8 w-8 text-slate-600" />
          <p className="mt-3 text-sm font-medium text-slate-300">
            No incidents found
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Send a stack trace to <code className="font-mono">POST /v1/incidents</code>{" "}
            to trigger autonomous remediation.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {incidents.map((incident) => (
            <IncidentCard key={incident.id} incident={incident} />
          ))}
        </div>
      )}
    </div>
  );
}

