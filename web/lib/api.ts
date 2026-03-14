import type {
  AdminAthleteRecord,
  AdminPlanSummary,
  MeResponse,
  PlanDetail,
  PlanRequest,
  PlanSummary,
  ProfileUpdateRequest,
} from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

type ApiRequestInit = RequestInit & {
  token?: string | null;
};

async function readJson<T>(path: string, init?: ApiRequestInit): Promise<T> {
  const headers = new Headers(init?.headers ?? {});
  headers.set("Content-Type", "application/json");
  if (init?.token) {
    headers.set("Authorization", `Bearer ${init.token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    cache: "no-store",
    headers,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }

  return (await response.json()) as T;
}

export function getMe(token: string): Promise<MeResponse> {
  return readJson<MeResponse>("/api/me", { token });
}

export function updateMe(token: string, payload: ProfileUpdateRequest): Promise<MeResponse> {
  return readJson<MeResponse>("/api/me", {
    method: "PUT",
    token,
    body: JSON.stringify(payload),
  });
}

export function generatePlan(token: string, payload: PlanRequest): Promise<PlanDetail> {
  return readJson<PlanDetail>("/api/plans/generate", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export function listPlans(token: string): Promise<PlanSummary[]> {
  return readJson<PlanSummary[]>("/api/plans", { token });
}

export function getPlan(token: string, planId: string): Promise<PlanDetail> {
  return readJson<PlanDetail>(`/api/plans/${planId}`, { token });
}

export function listAdminAthletes(token: string): Promise<AdminAthleteRecord[]> {
  return readJson<AdminAthleteRecord[]>("/api/admin/athletes", { token });
}

export function listAdminPlans(token: string): Promise<AdminPlanSummary[]> {
  return readJson<AdminPlanSummary[]>("/api/admin/plans", { token });
}