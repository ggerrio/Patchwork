import { Activity, Clock, Coins } from "lucide-react";

import type { AgentTrace } from "@/types/incident";

export function TraceTimeline({ traces }: { traces: AgentTrace[] }) {
  if (traces.length === 0) {
    return (
      <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6 text-sm text-slate-400">
        No agent execution traces recorded yet.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {traces.map((trace, index) => (
        <div
          key={trace.id}
          className="relative rounded-xl border border-slate-800 bg-slate-900/70 p-4"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2.5">
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-sky-950 text-xs font-semibold text-sky-300 border border-sky-800">
                {index + 1}
              </span>
              <span className="inline-flex items-center gap-1.5 font-mono text-sm font-semibold text-slate-100">
                <Activity className="h-4 w-4 text-sky-400" />
                {trace.step_name}
              </span>
            </div>

            <div className="flex items-center gap-4 text-xs text-slate-400">
              <span className="inline-flex items-center gap-1">
                <Clock className="h-3.5 w-3.5 text-slate-500" />
                {trace.latency_ms} ms
              </span>
              <span className="inline-flex items-center gap-1">
                <Coins className="h-3.5 w-3.5 text-slate-500" />
                {trace.tokens_used.toLocaleString()} tok
              </span>
              <span className="font-mono text-slate-500">
                {new Date(trace.created_at).toLocaleTimeString()}
              </span>
            </div>
          </div>

          <p className="mt-2.5 text-sm text-slate-200">{trace.thought_summary}</p>

          {trace.tool_output ? (
            <pre className="mt-3 max-h-48 overflow-auto rounded-lg border border-slate-800 bg-slate-950 p-3 font-mono text-xs text-slate-300">
              {trace.tool_output}
            </pre>
          ) : null}
        </div>
      ))}
    </div>
  );
}

