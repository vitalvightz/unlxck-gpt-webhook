import type {
  AdminAthleteRecord,
  AdminPlanSummary,
  ManualStage2SubmissionRequest,
  MeResponse,
  PlanDetail,
  PlanRequest,
  PlanSummary,
  ProfileUpdateRequest,
} from "@/lib/types";

const EXPLICIT_API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? null;
const LOCAL_API_BASE_URL = "http://127.0.0.1:8000";

function getApiBaseUrl(): string {
  if (typeof window !== "undefined") {
    return "";
  }

  return EXPLICIT_API_BASE_URL ?? LOCAL_API_BASE_URL;
}

type ApiRequestInit = RequestInit & {
  token?: string | null;
};

/** Error thrown for non-2xx HTTP responses. Includes the HTTP `status` code. */
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function truncateForLog(value: string, max = 1200): string {
  return value.length > max ? `${value.slice(0, max)}…[truncated]` : value;
}

async function readJson<T>(path: string, init?: ApiRequestInit): Promise<T> {
  const headers = new Headers(init?.headers ?? {});
  if (init?.body) {
    headers.set("Content-Type", "application/json");
  }
  if (init?.token) {
    headers.set("Authorization", `Bearer ${init.token}`);
  }

  const method = init?.method ?? "GET";
  const url = `${getApiBaseUrl()}${path}`;
  const startedAt = Date.now();

  console.info("[api] request:start", {
    path,
    method,
    url,
    hasBody: Boolean(init?.body),
    hasToken: Boolean(init?.token),
    startedAtIso: new Date(startedAt).toISOString(),
  });

  let response: Response;
  try {
    response = await fetch(url, {
      ...init,
      cache: "no-store",
      headers,
    });
  } catch (networkError) {
    const durationMs = Date.now() - startedAt;
    console.error("[api] request:network_error", {
      path,
      method,
      url,
      durationMs,
      online: typeof navigator !== "undefined" ? navigator.onLine : "unknown",
      error:
        networkError instanceof Error
          ? { name: networkError.name, message: networkError.message, stack: networkError.stack }
          : networkError,
    });
    throw new Error("Unable to reach the server. Please check your connection and try again.", {
      cause: networkError,
    });
  }

  const durationMs = Date.now() - startedAt;
  const contentType = response.headers.get("content-type") ?? "";
  const requestId = response.headers.get("x-request-id");

  if (!response.ok) {
    const rawText = await response.text();
    const trimmedText = rawText.trim();
    let parsedBody: unknown = null;

    if (trimmedText && contentType.includes("application/json")) {
      try {
        parsedBody = JSON.parse(trimmedText);
      } catch (parseError) {
        console.warn("[api] request:error_body_json_parse_failed", {
          path,
          method,
          url,
          requestId,
          status: response.status,
          contentType,
          durationMs,
          parseError:
            parseError instanceof Error
              ? { name: parseError.name, message: parseError.message }
              : parseError,
        });
      }
    }

    console.error("[api] request:failed", {
      path,
      method,
      url,
      requestId,
      status: response.status,
      statusText: response.statusText,
      contentType,
      durationMs,
      rawText: truncateForLog(trimmedText),
      parsedBody,
    });

    if (parsedBody && typeof parsedBody === "object" && parsedBody !== null) {
      const detail = "detail" in parsedBody ? (parsedBody as { detail?: unknown }).detail : null;
      const bodyRequestId =
        "request_id" in parsedBody ? (parsedBody as { request_id?: unknown }).request_id : null;

      if (typeof detail === "string") {
        throw new ApiError(
          bodyRequestId ? `${detail} (request id: ${String(bodyRequestId)})` : detail,
          response.status,
        );
      }

      if (detail != null) {
        throw new ApiError(
          bodyRequestId
            ? `${JSON.stringify(detail)} (request id: ${String(bodyRequestId)})`
            : JSON.stringify(detail),
          response.status,
        );
      }
    }

    throw new ApiError(
      requestId
        ? `${trimmedText || `Request failed: ${response.status}`} (request id: ${requestId})`
        : trimmedText || `Request failed: ${response.status}`,
      response.status,
    );
  }

  try {
    const data = (await response.json()) as T;
    console.info("[api] request:success", {
      path,
      method,
      url,
      requestId,
      status: response.status,
      durationMs,
    });
    return data;
  } catch (parseError) {
    console.error("[api] request:success_body_parse_failed", {
      path,
      method,
      url,
      requestId,
      status: response.status,
      contentType,
      durationMs,
      parseError:
        parseError instanceof Error
          ? { name: parseError.name, message: parseError.message, stack: parseError.stack }
          : parseError,
    });
    throw new Error("Server returned an unreadable response.");
  }
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

export function getAdminAthlete(token: string, athleteId: string): Promise<AdminAthleteRecord> {
  return readJson<AdminAthleteRecord>(`/api/admin/athletes/${athleteId}`, { token });
}

export function listAdminPlans(token: string): Promise<AdminPlanSummary[]> {
  return readJson<AdminPlanSummary[]>("/api/admin/plans", { token });
}

export function submitManualStage2(
  token: string,
  planId: string,
  payload: ManualStage2SubmissionRequest,
): Promise<PlanDetail> {
  return readJson<PlanDetail>(`/api/admin/plans/${planId}/manual-stage2`, {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export function approvePlanForRelease(token: string, planId: string): Promise<PlanDetail> {
  return readJson<PlanDetail>(`/api/admin/plans/${planId}/approve`, {
    method: "POST",
    token,
  });
}
