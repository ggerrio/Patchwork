import Link from "next/link";
import { ArrowRight, Coins, GitBranch, RotateCcw } from "lucide-react";

import { StatusBadge } from "@/components/StatusBadge";
import type { Incident } from "@/types/incident";

export function IncidentCard({ incident }: { incident: Incident }) {
  return (
    <Link
      href={`/incidents/${incident.id}`}
      className="group block rounded-xl border border-slate-800 bg-slate-900/70 p-4 transition hover:border-slate-600 hover:bg-slate-900"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
            <span className="inline-flex items-center gap-1 font-mono text-slate-300">
              <GitBranch className="h-3.5 w-3.5 text-slate-500" />
              {incident.repo_owner}/{incident.repo_name}
            </span>
            <span>•</span>
            <span className="font-mono">{incident.base_branch}</span>
            <span>•</span>
            <span className="font-mono text-slate-500">{incident.id.slice(0, 8)}</span>
          </div>

          <h3 className="mt-1.5 truncate text-base font-semibold text-slate-100 group-hover:text-sky-300">
            {incident.error_type}:{" "}
            <span className="font-normal text-slate-300">{incident.error_message}</span>
          </h3>
        </div>

        <StatusBadge status={incident.status} />
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-800/80 pt-3 text-xs text-slate-400">
        <div className="flex flex-wrap items-center gap-4">
          <span className="inline-flex items-center gap-1.5">
            <RotateCcw className="h-3.5 w-3.5 text-slate-500" />
            Retries: <strong className="text-slate-200">{incident.retry_count}/3</strong>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Coins className="h-3.5 w-3.5 text-slate-500" />
            Tokens:{" "}
            <strong className="text-slate-200">
              {incident.total_tokens.toLocaleString()}
            </strong>
          </span>
          <span>
            Created:{" "}
            <strong className="text-slate-300">
              {new Date(incident.created_at).toLocaleString()}
            </strong>
          </span>
        </div>

        <span className="inline-flex items-center gap-1 font-medium text-sky-400 group-hover:translate-x-0.5 transition">
          Inspect <ArrowRight className="h-3.5 w-3.5" />
        </span>
      </div>
    </Link>
  );
}

