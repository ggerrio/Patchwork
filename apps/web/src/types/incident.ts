export type IncidentStatus =
  | "QUEUED"
  | "INVESTIGATING"
  | "PATCHING"
  | "VERIFYING"
  | "AWAITING_APPROVAL"
  | "APPROVED_PR_OPENED"
  | "REJECTED"
  | "FAILED_MAX_RETRIES"
  | "ESCALATED_TO_HUMAN";

export interface AgentTrace {
  id: string;
  incident_id: string;
  step_name: string;
  thought_summary: string;
  tool_output: string | null;
  tokens_used: number;
  latency_ms: number;
  created_at: string;
}

export interface Incident {
  id: string;
  fingerprint: string;
  repo_owner: string;
  repo_name: string;
  base_branch: string;
  error_type: string;
  error_message: string;
  stack_trace: string;
  status: IncidentStatus;
  proposed_diff: string | null;
  patch_explanation: string | null;
  pr_url: string | null;
  retry_count: number;
  total_tokens: number;
  created_at: string;
  updated_at: string;
}

export interface IncidentDetail extends Incident {
  traces: AgentTrace[];
}

export interface IncidentListResponse {
  items: Incident[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApprovalActionResponse {
  id: string;
  status: IncidentStatus;
  pr_url: string | null;
  message: string;
}

export interface SystemHealthResponse {
  status: string;
  database: string;
  services?: {
    fastapi: boolean;
    supabase: boolean;
    redis: boolean;
    docker_sandbox: boolean;
    gemini_api: boolean;
  };
  duplicates_blocked?: number;
}
