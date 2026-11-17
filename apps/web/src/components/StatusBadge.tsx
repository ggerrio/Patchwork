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
  { label: string; className: string; dotClass: string; icon: typeof Clock }
> = {
  QUEUED: {
    label: "Queued",
    className: "bg-[#181B22] text-[#9CA3AF] border-[#23262F]",
    dotClass: "bg-[#9CA3AF]",
    icon: Clock,
  },
  INVESTIGATING: {
    label: "Investigating",
    className: "bg-[#DC2626]/10 text-[#F4F4F5] border-[#DC2626]/40",
    dotClass: "bg-[#DC2626]",
    icon: Loader2,
  },
  PATCHING: {
    label: "Patching",
    className: "bg-[#DC2626]/10 text-[#F4F4F5] border-[#DC2626]/40",
    dotClass: "bg-[#DC2626]",
    icon: Loader2,
  },
  VERIFYING: {
    label: "Verifying",
    className: "bg-[#DC2626]/10 text-[#F4F4F5] border-[#DC2626]/40",
    dotClass: "bg-[#DC2626]",
    icon: Loader2,
  },
  AWAITING_APPROVAL: {
    label: "Awaiting Approval",
    className: "bg-[#F59E0B]/10 text-[#F59E0B] border-[#F59E0B]/30",
    dotClass: "bg-[#F59E0B]",
    icon: CheckCircle2,
  },
  APPROVED_PR_OPENED: {
    label: "Pytest Passed • PR Opened",
    className: "bg-[#0F241D] text-[#10B981] border-[#10B981]/30",
    dotClass: "bg-[#10B981]",
    icon: GitPullRequest,
  },
  REJECTED: {
    label: "Rejected",
    className: "bg-[#261216] text-[#EF4444] border-[#EF4444]/30",
    dotClass: "bg-[#EF4444]",
    icon: XCircle,
  },
  FAILED_MAX_RETRIES: {
    label: "Failed (3/3)",
    className: "bg-[#261216] text-[#EF4444] border-[#EF4444]/30",
    dotClass: "bg-[#EF4444]",
    icon: AlertTriangle,
  },
  ESCALATED_TO_HUMAN: {
    label: "Escalated",
    className: "bg-[#F59E0B]/10 text-[#F59E0B] border-[#F59E0B]/30",
    dotClass: "bg-[#F59E0B]",
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
      className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 font-mono text-xs font-medium ${config.className}`}
    >
      <Icon className={`h-3.5 w-3.5 ${isSpinning ? "animate-spin" : ""}`} />
      {config.label}
    </span>
  );
}
