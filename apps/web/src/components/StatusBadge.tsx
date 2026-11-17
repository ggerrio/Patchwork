import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  GitPullRequest,
  Loader2,
  ShieldAlert,
  XCircle,
} from "lucide-react";

import type { IncidentStatus } from "@/types/incident";

const STATUS_STYLES: Record<
  IncidentStatus,
  { label: string; className: string; icon: typeof Clock }
> = {
  QUEUED: {
    label: "Queued",
    className: "bg-slate-800 text-slate-300 border-slate-700",
    icon: Clock,
  },
  INVESTIGATING: {
    label: "Investigating",
    className: "bg-sky-950/70 text-sky-300 border-sky-800",
    icon: Loader2,
  },
  PATCHING: {
    label: "Patching",
    className: "bg-indigo-950/70 text-indigo-300 border-indigo-800",
    icon: Loader2,
  },
  VERIFYING: {
    label: "Verifying",
    className: "bg-cyan-950/70 text-cyan-300 border-cyan-800",
    icon: Loader2,
  },
  AWAITING_APPROVAL: {
    label: "Awaiting Approval",
    className: "bg-amber-950/70 text-amber-300 border-amber-700",
    icon: CheckCircle2,
  },
  APPROVED_PR_OPENED: {
    label: "PR Opened",
    className: "bg-emerald-950/70 text-emerald-300 border-emerald-700",
    icon: GitPullRequest,
  },
  REJECTED: {
    label: "Rejected",
    className: "bg-rose-950/70 text-rose-300 border-rose-800",
    icon: XCircle,
  },
  FAILED_MAX_RETRIES: {
    label: "Failed (Max Retries)",
    className: "bg-red-950/70 text-red-300 border-red-800",
    icon: AlertTriangle,
  },
  ESCALATED_TO_HUMAN: {
    label: "Escalated to Human",
    className: "bg-fuchsia-950/70 text-fuchsia-300 border-fuchsia-800",
    icon: ShieldAlert,
  },
};

export function StatusBadge({ status }: { status: IncidentStatus }) {
  const config = STATUS_STYLES[status];
  const Icon = config.icon;
  const isSpinning =
    status === "INVESTIGATING" || status === "PATCHING" || status === "VERIFYING";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${config.className}`}
    >
      <Icon className={`h-3.5 w-3.5 ${isSpinning ? "animate-spin" : ""}`} />
      {config.label}
    </span>
  );
}

