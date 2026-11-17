import { ArrowRight, Coins, GitBranch, RotateCcw } from "lucide-react";

import { StatusBadge } from "@/components/StatusBadge";
import type { Incident } from "@/types/incident";

interface IncidentCardProps {
  incident: Incident;
  onSelect?: (id: string) => void;
}

export function IncidentCard({ incident, onSelect }: IncidentCardProps) {
  const isActive =
    incident.status === "INVESTIGATING" ||
    incident.status === "PATCHING" ||
    incident.status === "VERIFYING" ||
    incident.status === "AWAITING_APPROVAL";

  return (
    <button
      type="button"
      onClick={() => onSelect?.(incident.id)}
      className={`tactile-card group flex w-full items-center justify-between gap-4 rounded-lg p-5 text-left transition hover:border-[#373B47] hover:bg-[#171A21] ${
        isActive ? "border-l-2 border-l-[#DC2626]" : ""
      }`}
    >
      <div className="min-w-0 flex-1 space-y-2">
        <div className="flex flex-wrap items-center gap-3 font-mono text-xs text-[#9CA3AF]">
          <span className="inline-flex items-center gap-1.5 text-[#F4F4F5]">
            <GitBranch className="h-3.5 w-3.5 text-[#DC2626]" />
            {incident.repo_owner}/{incident.repo_name}
          </span>
          <span className="text-[#2E323E]">•</span>
          <span>#{incident.id.slice(0, 8)}</span>
          <span className="text-[#2E323E]">•</span>
          <span className="inline-flex items-center gap-1">
            <RotateCcw className="h-3 w-3" />
            {incident.retry_count}/3
          </span>
          <span className="text-[#2E323E]">•</span>
          <span className="inline-flex items-center gap-1">
            <Coins className="h-3 w-3" />
            {incident.total_tokens.toLocaleString()} tok
          </span>
          <span className="text-[#2E323E]">•</span>
          <span>{new Date(incident.created_at).toLocaleString()}</span>
        </div>

        <h3 className="truncate text-base font-semibold text-[#F4F4F5]">
          <span className="font-mono text-[#EF4444]">{incident.error_type}</span>
          :{" "}
          <span className="font-normal text-[#F4F4F5]">
            {incident.error_message}
          </span>
        </h3>
      </div>

      <div className="flex shrink-0 items-center gap-4">
        <StatusBadge status={incident.status} />
        <ArrowRight className="h-4 w-4 text-[#9CA3AF] transition group-hover:translate-x-0.5 group-hover:text-[#F4F4F5]" />
      </div>
    </button>
  );
}
