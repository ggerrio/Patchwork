"use client";

import { useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Coins,
  Terminal,
  XCircle,
} from "lucide-react";

import type { AgentTrace } from "@/types/incident";

export function TraceTimeline({ traces }: { traces: AgentTrace[] }) {
  const [openIds, setOpenIds] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {};
    traces.forEach((t, idx) => {
      if (t.step_name === "sandbox_node" || idx === traces.length - 1) {
        initial[t.id] = true;
      }
    });
    return initial;
  });

  if (traces.length === 0) {
    return (
      <div className="tactile-card rounded-lg p-6 text-sm text-[#9CA3AF]">
        No agent execution steps recorded yet.
      </div>
    );
  }

  function toggle(id: string) {
    setOpenIds((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  return (
    <div className="space-y-4">
      {/* Horizontal Pipeline Step Strip */}
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {traces.slice(0, 4).map((trace, idx) => {
          const isFailed =
            trace.step_name.includes("error") ||
            trace.step_name.includes("rejected") ||
            trace.thought_summary.toUpperCase().includes("FAILED");
          return (
            <div
              key={trace.id}
              className="tactile-card flex items-center justify-between rounded-lg px-3.5 py-2.5"
            >
              <div className="min-w-0">
                <div className="font-mono text-[10px] uppercase tracking-wider text-[#9CA3AF]">
                  STEP 0{idx + 1}
                </div>
                <div className="truncate font-mono text-xs font-semibold text-[#F4F4F5]">
                  {trace.step_name}
                </div>
              </div>
              <span
                className={`h-2 w-2 shrink-0 rounded-full ${
                  isFailed ? "bg-[#EF4444]" : "bg-[#10B981]"
                }`}
              />
            </div>
          );
        })}
      </div>

      {/* Collapsible Vertical Step Cards */}
      <div className="space-y-3">
        {traces.map((trace, index) => {
          const isOpen = Boolean(openIds[trace.id]);
          const isFailed =
            trace.step_name.includes("error") ||
            trace.step_name.includes("rejected") ||
            trace.thought_summary.toUpperCase().includes("FAILED");
          const isSandbox = trace.step_name === "sandbox_node";

          return (
            <div
              key={trace.id}
              className="tactile-card overflow-hidden rounded-lg"
            >
              <button
                type="button"
                onClick={() => toggle(trace.id)}
                className="flex w-full items-center justify-between gap-4 px-4 py-3.5 text-left transition hover:bg-[#181B22]"
              >
                <div className="flex min-w-0 items-center gap-3">
                  {isOpen ? (
                    <ChevronDown className="h-4 w-4 shrink-0 text-[#9CA3AF]" />
                  ) : (
                    <ChevronRight className="h-4 w-4 shrink-0 text-[#9CA3AF]" />
                  )}

                  {isFailed ? (
                    <XCircle className="h-4 w-4 shrink-0 text-[#EF4444]" />
                  ) : (
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-[#10B981]" />
                  )}

                  <span className="rounded bg-[#0B0C0E] px-1.5 py-0.5 font-mono text-[11px] text-[#9CA3AF]">
                    0{index + 1}
                  </span>

                  <span className="font-mono text-sm font-medium text-[#F4F4F5]">
                    {trace.step_name}
                  </span>

                  <span className="hidden truncate text-sm text-[#9CA3AF] md:inline">
                    — {trace.thought_summary.replace(/\s*\[prompt_tokens=.*\]$/, "")}
                  </span>
                </div>

                <div className="flex shrink-0 items-center gap-4 font-mono text-xs text-[#9CA3AF]">
                  <span className="inline-flex items-center gap-1">
                    <Clock className="h-3.5 w-3.5" />
                    {trace.latency_ms}ms
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <Coins className="h-3.5 w-3.5" />
                    {trace.tokens_used.toLocaleString()} tok
                  </span>
                </div>
              </button>

              {isOpen ? (
                <div className="space-y-3 border-t border-[#23262F] bg-[#0B0C0E] px-4 py-4">
                  <p className="text-sm leading-relaxed text-[#F4F4F5]">
                    {trace.thought_summary}
                  </p>

                  {trace.tool_output ? (
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between text-xs font-mono text-[#9CA3AF]">
                        <span className="inline-flex items-center gap-1.5">
                          <Terminal className="h-3.5 w-3.5 text-[#DC2626]" />
                          {isSandbox
                            ? "DOCKER SANDBOX // PYTEST LOG"
                            : "NODE PAYLOAD"}
                        </span>
                        {isSandbox ? (
                          <span
                            className={
                              isFailed ? "text-[#EF4444]" : "text-[#10B981]"
                            }
                          >
                            {isFailed ? "EXIT 1" : "EXIT 0"}
                          </span>
                        ) : null}
                      </div>
                      <pre className="max-h-72 overflow-auto rounded-md border border-[#23262F] bg-[#13151A] p-3.5 font-mono text-xs leading-relaxed text-[#F4F4F5]">
                        {trace.tool_output}
                      </pre>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}
