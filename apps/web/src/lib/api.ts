import type {
  ApprovalActionResponse,
  IncidentDetail,
  IncidentListResponse,
  IncidentStatus,
} from "@/types/incident";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") || "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API ${response.status}: ${text || response.statusText}`);
  }

  return (await response.json()) as T;
}

export async function listIncidents(params?: {
  status?: IncidentStatus | "ALL";
  limit?: number;
  offset?: number;
}): Promise<IncidentListResponse> {
  const search = new URLSearchParams();
  if (params?.status && params.status !== "ALL") {
    search.set("status", params.status);
  }
  if (params?.limit !== undefined) {
    search.set("limit", String(params.limit));
  }
  if (params?.offset !== undefined) {
    search.set("offset", String(params.offset));
  }
  const qs = search.toString();
  return apiFetch<IncidentListResponse>(`/v1/incidents${qs ? `?${qs}` : ""}`);
}

export async function getIncident(id: string): Promise<IncidentDetail> {
  return apiFetch<IncidentDetail>(`/v1/incidents/${encodeURIComponent(id)}`);
}

export async function approveIncident(id: string): Promise<ApprovalActionResponse> {
  return apiFetch<ApprovalActionResponse>(`/v1/incidents/${encodeURIComponent(id)}/approve`, {
    method: "POST",
  });
}

export async function rejectIncident(
  id: string,
  reason: string
): Promise<ApprovalActionResponse> {
  return apiFetch<ApprovalActionResponse>(`/v1/incidents/${encodeURIComponent(id)}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

