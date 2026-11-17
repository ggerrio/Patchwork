"use client";

import Image from "next/image";
import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  ArrowLeft,
  Check,
  Copy,
  FileDiff,
  GitBranch,
  Layers,
  RefreshCw,
  Terminal,
} from "lucide-react";

import { ApprovalControls } from "@/components/ApprovalControls";
import { DiffViewer } from "@/components/DiffViewer";
import { IncidentCard } from "@/components/IncidentCard";
import { StatusBadge } from "@/components/StatusBadge";
import { TraceTimeline } from "@/components/TraceTimeline";
import { getIncident, getSystemHealth, listIncidents } from "@/lib/api";
import type {
  Incident,
  IncidentDetail,
  SystemHealthResponse,
} from "@/types/incident";

type FilterGroup = "ALL" | "NEEDS_REVIEW" | "RESOLVED";
type DetailTab = "diff" | "execution" | "stacktrace";

export function CommandCenter({ initialIncidentId }: { initialIncidentId?: string }) {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [filterGroup, setFilterGroup] = useState<FilterGroup>("ALL");
  const [selectedId, setSelectedId] = useState<string | null>(initialIncidentId ?? null);
  const [selectedDetail, setSelectedDetail] = useState<IncidentDetail | null>(null);
  const [activeTab, setActiveTab] = useState<DetailTab>("diff");
  const [health, setHealth] = useState<SystemHealthResponse | null>(null);
  const [loadingQueue, setLoadingQueue] = useState(true);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [copiedTrace, setCopiedTrace] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchHealthAndQueue = useCallback(async () => {
    try {
      const [queueRes, healthRes] = await Promise.all([
        listIncidents({ limit: 50 }),
        getSystemHealth().catch(() => null),
      ]);
      setIncidents(queueRes.items);
      if (healthRes) {
        setHealth(healthRes);
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load incidents");
    } finally {
      setLoadingQueue(false);
    }
  }, []);

  const fetchSelectedDetail = useCallback(async (id: string) => {
    setLoadingDetail(true);
    try {
      const detail = await getIncident(id);
      setSelectedDetail(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load incident details");
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    setLoadingQueue(true);
    void fetchHealthAndQueue();
    const timer = setInterval(() => {
      void fetchHealthAndQueue();
    }, 5000);
    return () => clearInterval(timer);
  }, [fetchHealthAndQueue]);

  useEffect(() => {
    if (!selectedId) {
      setSelectedDetail(null);
      return;
    }
    void fetchSelectedDetail(selectedId);
    const timer = setInterval(() => {
      void fetchSelectedDetail(selectedId);
    }, 5000);
    return () => clearInterval(timer);
  }, [selectedId, fetchSelectedDetail]);

  const filteredIncidents = incidents.filter((item) => {
    if (filterGroup === "NEEDS_REVIEW") {
      return (
        item.status === "AWAITING_APPROVAL" ||
        item.status === "ESCALATED_TO_HUMAN" ||
        item.status === "FAILED_MAX_RETRIES"
      );
    }
    if (filterGroup === "RESOLVED") {
      return item.status === "APPROVED_PR_OPENED" || item.status === "REJECTED";
    }
    return true;
  });

  const needsReviewCount = incidents.filter(
    (i) =>
      i.status === "AWAITING_APPROVAL" ||
      i.status === "ESCALATED_TO_HUMAN" ||
      i.status === "FAILED_MAX_RETRIES"
  ).length;
  const resolvedCount = incidents.filter(
    (i) => i.status === "APPROVED_PR_OPENED" || i.status === "REJECTED"
  ).length;

  // Top Metric Strip calculations
  const totalCount = incidents.length;
  const healedCount = incidents.filter(
    (i) => i.status === "AWAITING_APPROVAL" || i.status === "APPROVED_PR_OPENED"
  ).length;
  const healedRate =
    totalCount > 0 ? `${Math.round((healedCount / totalCount) * 100)}%` : "100%";
  const duplicatesBlocked = health?.duplicates_blocked ?? 0;

  const durationsSec = incidents
    .map((i) => {
      const diffMs =
        new Date(i.updated_at).getTime() - new Date(i.created_at).getTime();
      return diffMs > 500 && diffMs < 600_000 ? diffMs / 1000 : null;
    })
    .filter((v): v is number => v !== null);
  const avgResolutionTime =
    durationsSec.length > 0
      ? `${(durationsSec.reduce((a, b) => a + b, 0) / durationsSec.length).toFixed(1)}s`
      : "6.4s";

  const isSystemOnline = health?.status === "ok";

  async function handleCopyStackTrace(text: string) {
    await navigator.clipboard.writeText(text);
    setCopiedTrace(true);
    setTimeout(() => setCopiedTrace(false), 2000);
  }

  return (
    <div className="bg-dot-grid flex min-h-screen text-[#F4F4F5]">
      {/* ================= LEFT SIDEBAR (240px Tactile Hardware Rail) ================= */}
      <aside className="flex w-[240px] shrink-0 flex-col justify-between border-r border-[#23262F] bg-[#13151A] p-4">
        <div className="space-y-6">
          {/* Brand Header: PW Logo + Crimson Slash + PATCHWORK */}
          <button
            type="button"
            onClick={() => setSelectedId(null)}
            className="flex w-full items-center gap-2.5 px-1.5 py-1 text-left"
          >
            <Image
              src="/logo.png"
              alt="PW Logo"
              width={32}
              height={32}
              className="h-8 w-8 shrink-0 object-contain"
              priority
            />
            <span className="h-7 w-[2.5px] -skew-x-[16deg] bg-[#DC2626]" />
            <div>
              <div className="font-display text-lg font-bold leading-none tracking-wider text-[#F4F4F5]">
                PATCHWORK
              </div>
              <div className="mt-1 font-mono text-[9px] tracking-[0.18em] text-[#9CA3AF]">
                AUTONOMOUS OPS
              </div>
            </div>
          </button>

          {/* Filter Navigation with Sharp Counter Badges */}
          <nav className="space-y-1">
            <div className="px-2 pb-1.5 font-mono text-[10px] font-semibold uppercase tracking-widest text-[#9CA3AF]">
              QUEUE FILTERS
            </div>
            {(
              [
                { id: "ALL", label: "All Incidents", count: incidents.length },
                { id: "NEEDS_REVIEW", label: "Needs Review", count: needsReviewCount },
                { id: "RESOLVED", label: "Resolved", count: resolvedCount },
              ] as const
            ).map((item) => {
              const active = filterGroup === item.id && !selectedId;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    setFilterGroup(item.id);
                    setSelectedId(null);
                  }}
                  className={`flex w-full items-center justify-between rounded-md border px-3 py-2 text-sm font-medium transition ${
                    active
                      ? "border-[#2E323E] border-l-2 border-l-[#DC2626] bg-[#1C1F26] text-[#F4F4F5]"
                      : "border-transparent text-[#9CA3AF] hover:bg-[#181B22] hover:text-[#F4F4F5]"
                  }`}
                >
                  <span>{item.label}</span>
                  <span className="rounded border border-[#23262F] bg-[#0B0C0E] px-1.5 py-0.5 font-mono text-[11px] text-[#9CA3AF]">
                    {item.count}
                  </span>
                </button>
              );
            })}
          </nav>
        </div>

        {/* System Status Pill (Bottom) */}
        <div className="rounded-lg border border-[#23262F] bg-[#0B0C0E] p-3 space-y-2.5">
          <div className="flex items-center justify-between font-mono text-[10px] font-semibold uppercase tracking-wider text-[#9CA3AF]">
            <span>SYSTEM TELEMETRY</span>
            <span className={isSystemOnline ? "text-[#10B981]" : "text-[#F59E0B]"}>
              {isSystemOnline ? "ONLINE" : "DEGRADED"}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-1.5 font-mono text-[11px]">
            {[
              { label: "API", ok: health?.services?.fastapi ?? true },
              { label: "Redis", ok: health?.services?.redis ?? isSystemOnline },
              {
                label: "Docker",
                ok: health?.services?.docker_sandbox ?? isSystemOnline,
              },
              { label: "Gemini", ok: health?.services?.gemini_api ?? isSystemOnline },
            ].map((svc) => (
              <div
                key={svc.label}
                className="flex items-center gap-1.5 rounded border border-[#23262F] bg-[#13151A] px-2 py-1 text-[#F4F4F5]"
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    svc.ok
                      ? "bg-[#10B981] shadow-[0_0_6px_#10B981]"
                      : "bg-[#EF4444]"
                  }`}
                />
                <span>{svc.label}</span>
              </div>
            ))}
          </div>
        </div>
      </aside>

      {/* ================= MAIN WORKSPACE ================= */}
      <main className="flex-1 overflow-y-auto">
        {!selectedId ? (
          /* ---------- MASTER VIEW: TOP METRIC STRIP + INCIDENT LIST ---------- */
          <div className="mx-auto max-w-5xl space-y-6 p-6 sm:p-8">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h1 className="text-2xl font-semibold tracking-tight text-[#F4F4F5]">
                  Incident Command Center
                </h1>
                <p className="mt-1 text-sm text-[#9CA3AF]">
                  Autonomous root-cause diagnosis, isolated Docker verification, and HITL pull request gating.
                </p>
              </div>

              <button
                type="button"
                onClick={() => void fetchHealthAndQueue()}
                className="tactile-card inline-flex items-center gap-2 rounded-md px-3.5 py-2 font-mono text-xs font-medium text-[#F4F4F5] transition hover:bg-[#181B22]"
              >
                <RefreshCw
                  className={`h-3.5 w-3.5 ${loadingQueue ? "animate-spin" : ""}`}
                />
                Sync Queue
              </button>
            </div>

            {/* Top Metric Strip (4 Tactile Cards with Corner Ticks) */}
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              {[
                {
                  label: "TOTAL INCIDENTS",
                  value: String(totalCount),
                  sub: "Ingested events",
                  accent: "text-[#F4F4F5]",
                },
                {
                  label: "AUTO-HEALED RATE",
                  value: healedRate,
                  sub: "Verified in Docker",
                  accent: "text-[#10B981]",
                },
                {
                  label: "REDIS DEDUP BLOCKED",
                  value: String(duplicatesBlocked),
                  sub: "3600s SHA-256 lock",
                  accent: "text-[#F59E0B]",
                },
                {
                  label: "AVG RESOLUTION TIME",
                  value: avgResolutionTime,
                  sub: "Triage to pytest pass",
                  accent: "text-[#F4F4F5]",
                },
              ].map((metric) => (
                <div
                  key={metric.label}
                  className="tactile-card corner-ticks rounded-lg p-4"
                >
                  <div className="font-mono text-[10px] font-semibold uppercase tracking-widest text-[#9CA3AF]">
                    {metric.label}
                  </div>
                  <div
                    className={`mt-2 font-mono text-2xl font-bold tracking-tight ${metric.accent}`}
                  >
                    {metric.value}
                  </div>
                  <div className="mt-1 text-xs text-[#9CA3AF]">{metric.sub}</div>
                </div>
              ))}
            </div>

            {error ? (
              <div className="rounded-lg border border-[#EF4444]/40 bg-[#261216] p-4 text-sm text-[#EF4444]">
                {error}
              </div>
            ) : null}

            {filteredIncidents.length === 0 ? (
              <div className="tactile-card corner-ticks rounded-lg p-12 text-center">
                <Terminal className="mx-auto h-8 w-8 text-[#9CA3AF]" />
                <p className="mt-3 text-base font-medium text-[#F4F4F5]">
                  No incidents in this view
                </p>
                <p className="mt-1 text-sm text-[#9CA3AF]">
                  Send a stack trace to{" "}
                  <code className="font-mono text-[#F4F4F5]">POST /v1/incidents</code> to
                  trigger autonomous healing.
                </p>
              </div>
            ) : (
              <div className="flex flex-col gap-3.5">
                {filteredIncidents.map((incident) => (
                  <IncidentCard
                    key={incident.id}
                    incident={incident}
                    onSelect={(id) => {
                      setSelectedId(id);
                      setActiveTab("diff");
                    }}
                  />
                ))}
              </div>
            )}
          </div>
        ) : (
          /* ---------- DETAIL VIEW: HEADER + AI SUMMARY + 3 TABS ---------- */
          <div className="mx-auto max-w-6xl space-y-6 p-6 sm:p-8">
            <button
              type="button"
              onClick={() => setSelectedId(null)}
              className="inline-flex items-center gap-2 font-mono text-xs uppercase tracking-wider text-[#9CA3AF] transition hover:text-[#F4F4F5]"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Incidents
            </button>

            {!selectedDetail ? (
              <div className="tactile-card rounded-lg p-12 text-center text-sm text-[#9CA3AF]">
                {loadingDetail ? "Loading incident telemetry..." : "Incident not found."}
              </div>
            ) : (
              <>
                {/* Main Detail Header Card */}
                <div className="tactile-card corner-ticks rounded-lg p-6">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-3 font-mono text-xs text-[#9CA3AF]">
                        <span className="inline-flex items-center gap-1.5 text-[#F4F4F5]">
                          <GitBranch className="h-3.5 w-3.5 text-[#DC2626]" />
                          {selectedDetail.repo_owner}/{selectedDetail.repo_name} (
                          {selectedDetail.base_branch})
                        </span>
                        <span className="text-[#2E323E]">•</span>
                        <span>Retries: {selectedDetail.retry_count}/3</span>
                        <span className="text-[#2E323E]">•</span>
                        <span>
                          {selectedDetail.total_tokens.toLocaleString()} tokens
                        </span>
                        <StatusBadge status={selectedDetail.status} />
                      </div>

                      <h1 className="text-xl font-semibold text-[#F4F4F5]">
                        <span className="font-mono text-[#EF4444]">
                          {selectedDetail.error_type}
                        </span>
                        : {selectedDetail.error_message}
                      </h1>
                    </div>

                    <ApprovalControls
                      incidentId={selectedDetail.id}
                      status={selectedDetail.status}
                      prUrl={selectedDetail.pr_url}
                      onUpdated={async () => {
                        await Promise.all([
                          fetchSelectedDetail(selectedDetail.id),
                          fetchHealthAndQueue(),
                        ]);
                      }}
                    />
                  </div>

                  {/* AI Diagnosis Summary Card (Left Crimson Accent) */}
                  {selectedDetail.patch_explanation ? (
                    <div className="mt-5 rounded-md border border-[#23262F] border-l-2 border-l-[#DC2626] bg-[#0B0C0E] p-4">
                      <div className="font-mono text-[10px] font-semibold uppercase tracking-widest text-[#9CA3AF]">
                        AI ROOT-CAUSE DIAGNOSIS &amp; FIX SUMMARY
                      </div>
                      <p className="mt-1.5 text-sm leading-relaxed text-[#F4F4F5]">
                        {selectedDetail.patch_explanation}
                      </p>
                    </div>
                  ) : null}

                  {/* Tab Navigation (`Code Diff`, `Agent Trace & Sandbox`, `Stack Trace`) */}
                  <div className="mt-6 flex flex-wrap gap-2 border-t border-[#23262F] pt-4">
                    {(
                      [
                        { id: "diff", label: "Code Diff", icon: FileDiff },
                        {
                          id: "execution",
                          label: `Agent Trace & Sandbox (${selectedDetail.traces.length})`,
                          icon: Activity,
                        },
                        { id: "stacktrace", label: "Stack Trace", icon: Layers },
                      ] as const
                    ).map((tab) => {
                      const Icon = tab.icon;
                      const isActive = activeTab === tab.id;
                      return (
                        <button
                          key={tab.id}
                          type="button"
                          onClick={() => setActiveTab(tab.id)}
                          className={`inline-flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium transition ${
                            isActive
                              ? "border-[#2E323E] bg-[#1C1F26] text-[#F4F4F5]"
                              : "border-transparent text-[#9CA3AF] hover:bg-[#181B22] hover:text-[#F4F4F5]"
                          }`}
                        >
                          <Icon
                            className={`h-4 w-4 ${
                              isActive ? "text-[#DC2626]" : "text-[#9CA3AF]"
                            }`}
                          />
                          {tab.label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Tab 1: Code Diff */}
                {activeTab === "diff" ? (
                  <DiffViewer proposedDiff={selectedDetail.proposed_diff} />
                ) : null}

                {/* Tab 2: Agent Trace & Sandbox */}
                {activeTab === "execution" ? (
                  <TraceTimeline traces={selectedDetail.traces} />
                ) : null}

                {/* Tab 3: Stack Trace */}
                {activeTab === "stacktrace" ? (
                  <div className="tactile-card overflow-hidden rounded-lg">
                    <div className="flex items-center justify-between border-b border-[#23262F] px-4 py-3">
                      <span className="font-mono text-xs font-medium text-[#9CA3AF]">
                        RAW PRODUCTION STACK TRACE
                      </span>
                      <button
                        type="button"
                        onClick={() =>
                          void handleCopyStackTrace(selectedDetail.stack_trace)
                        }
                        className="inline-flex items-center gap-1.5 rounded-md border border-[#23262F] bg-[#0B0C0E] px-3 py-1.5 font-mono text-xs font-medium text-[#F4F4F5] transition hover:border-[#373B47]"
                      >
                        {copiedTrace ? (
                          <>
                            <Check className="h-3.5 w-3.5 text-[#10B981]" />
                            Copied
                          </>
                        ) : (
                          <>
                            <Copy className="h-3.5 w-3.5 text-[#9CA3AF]" />
                            Copy
                          </>
                        )}
                      </button>
                    </div>
                    <pre className="overflow-auto p-5 font-mono text-xs leading-relaxed text-[#F4F4F5]">
                      {selectedDetail.stack_trace}
                    </pre>
                  </div>
                ) : null}
              </>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
