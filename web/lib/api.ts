import type {
  ApproveAndResumeGenerationRequest,
  AdminAthleteRecord,
  AdminPlanSummary,
  ManualStage2SubmissionRequest,
  GenerationJobResponse,
  MeResponse,
  NutritionWorkspaceState,
  NutritionWorkspaceUpdateRequest,
  PlanDetail,
  PlanRequest,
  PlanSummary,
  ProfileUpdateRequest,
} from "@/lib/types";

const EXPLICIT_API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? null;
const LOCAL_API_BASE_URL = "http://127.0.0.1:8000";

function getApiBaseUrl(): string {
  if (typeof window !== "undefined") {
    // Keep browser requests same-origin so Next.js rewrites can proxy /api calls.
    // This avoids direct cross-origin calls that can fail due to CORS/SSL mismatches.
    return "";
  }

  if (EXPLICIT_API_BASE_URL) {
    return EXPLICIT_API_BASE_URL;
  }

  if (process.env.NODE_ENV !== "production") {
    return LOCAL_API_BASE_URL;
  }

  throw new Error("NEXT_PUBLIC_API_BASE_URL must be set for server-side API calls in production.");
}

type ApiRequestInit = RequestInit & {
  token?: string | null;
  clientRequestId?: string | null;
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

const RETRYABLE_GATEWAY_STATUSES = new Set([502, 503, 504]);
const RETRYABLE_NETWORK_MESSAGE = "Unable to reach the server. Please check your connection and try again.";

function looksLikeHtmlErrorPage(contentType: string, body: string): boolean {
  return contentType.includes("text/html") || /^<!doctype html/i.test(body);
}

function extractHtmlRequestId(body: string): string | null {
  const match = body.match(/Request ID:\s*([A-Za-z0-9-]+)/i);
  return match?.[1] ?? null;
}

function formatGatewayErrorMessage(status: number, requestId: string | null): string {
  const baseMessage =
    status === 502
      ? "The plan service is temporarily unavailable. Please try again in a minute."
      : "The plan service is taking longer than expected. Please try again in a minute.";
  return requestId ? `${baseMessage} (request id: ${requestId})` : baseMessage;
}

function buildPlainTextErrorMessage(params: {
  status: number;
  contentType: string;
  trimmedText: string;
  headerRequestId: string | null;
}): string {
  const { status, contentType, trimmedText, headerRequestId } = params;

  if (looksLikeHtmlErrorPage(contentType, trimmedText)) {
    const requestId = headerRequestId ?? extractHtmlRequestId(trimmedText);
    return formatGatewayErrorMessage(status, requestId);
  }

  return headerRequestId
    ? `${trimmedText || `Request failed: ${status}`} (request id: ${headerRequestId})`
    : trimmedText || `Request failed: ${status}`;
}

export function isRetryableApiFailure(error: unknown): boolean {
  if (error instanceof ApiError) {
    return RETRYABLE_GATEWAY_STATUSES.has(error.status);
  }
  return error instanceof Error && error.message === RETRYABLE_NETWORK_MESSAGE;
}

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => globalThis.setTimeout(resolve, ms));
}

async function withTransientRetries<T>(
  operation: () => Promise<T>,
  {
    attempts = 3,
    delayMs = 1500,
  }: {
    attempts?: number;
    delayMs?: number;
  } = {},
): Promise<T> {
  let lastError: unknown;

  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await operation();
    } catch (error) {
      lastError = error;
      if (!isRetryableApiFailure(error) || attempt === attempts) {
        throw error;
      }
      await sleep(delayMs * attempt);
    }
  }

  throw lastError instanceof Error ? lastError : new Error("Request failed.");
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
  if (init?.clientRequestId) {
    headers.set("X-Client-Request-Id", init.clientRequestId);
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
    throw new Error(RETRYABLE_NETWORK_MESSAGE, {
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
      buildPlainTextErrorMessage({
        status: response.status,
        contentType,
        trimmedText,
        headerRequestId: requestId,
      }),
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

export function getNutritionCurrent(token: string): Promise<NutritionWorkspaceState> {
  return readJson<NutritionWorkspaceState>("/api/nutrition/current", { token });
}

export function updateNutritionCurrent(
  token: string,
  payload: NutritionWorkspaceUpdateRequest,
): Promise<NutritionWorkspaceState> {
  return readJson<NutritionWorkspaceState>("/api/nutrition/current", {
    method: "PUT",
    token,
    body: JSON.stringify(payload),
  });
}

export function createGenerationJob(
  token: string,
  payload: PlanRequest,
  clientRequestId?: string,
): Promise<GenerationJobResponse> {
  return withTransientRetries(() =>
    readJson<GenerationJobResponse>("/api/plans/generate", {
      method: "POST",
      token,
      clientRequestId,
      body: JSON.stringify(payload),
    }),
  );
}


export function getGenerationJob(token: string, jobId: string): Promise<GenerationJobResponse> {
  return withTransientRetries(() =>
    readJson<GenerationJobResponse>(`/api/generation-jobs/${jobId}`, { token }),
  );
}

export function listPlans(token: string): Promise<PlanSummary[]> {
  return readJson<PlanSummary[]>("/api/plans", { token });
}

export function getPlan(token: string, planId: string): Promise<PlanDetail> {
  return readJson<PlanDetail>(`/api/plans/${planId}`, { token });
}

export function renamePlan(token: string, planId: string, planName: string): Promise<PlanDetail> {
  return withTransientRetries(() =>
    readJson<PlanDetail>(`/api/plans/${planId}`, {
      method: "PATCH",
      token,
      body: JSON.stringify({ plan_name: planName }),
    }),
  );
}

export async function deletePlan(token: string, planId: string): Promise<void> {
  return withTransientRetries(async () => {
    const headers = new Headers();
    headers.set("Authorization", `Bearer ${token}`);

    const response = await fetch(`${getApiBaseUrl()}/api/plans/${planId}`, {
      method: "DELETE",
      cache: "no-store",
      headers,
    });

    if (!response.ok) {
      const message = (await response.text()).trim() || `Request failed: ${response.status}`;
      throw new ApiError(message, response.status);
    }
  });
}

export function listAdminAthletes(token: string): Promise<AdminAthleteRecord[]> {
  return readJson<AdminAthleteRecord[]>("/api/admin/athletes", { token });
}

export function getAdminAthlete(token: string, athleteId: string): Promise<AdminAthleteRecord> {
  return readJson<AdminAthleteRecord>(`/api/admin/athletes/${athleteId}`, { token });
}

export function getAdminAthleteNutritionCurrent(
  token: string,
  athleteId: string,
): Promise<NutritionWorkspaceState> {
  return readJson<NutritionWorkspaceState>(`/api/admin/athletes/${athleteId}/nutrition/current`, { token });
}

export function updateAdminAthleteNutritionCurrent(
  token: string,
  athleteId: string,
  payload: NutritionWorkspaceUpdateRequest,
): Promise<NutritionWorkspaceState> {
  return readJson<NutritionWorkspaceState>(`/api/admin/athletes/${athleteId}/nutrition/current`, {
    method: "PUT",
    token,
    body: JSON.stringify(payload),
  });
}

export function generateAdminAthletePlanFromLatestIntake(
  token: string,
  athleteId: string,
  clientRequestId?: string,
): Promise<GenerationJobResponse> {
  return withTransientRetries(() =>
    readJson<GenerationJobResponse>(`/api/admin/athletes/${athleteId}/plans/generate-from-latest-intake`, {
      method: "POST",
      token,
      clientRequestId,
    }),
  );
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

export function approvePlanForStage2(token: string, planId: string): Promise<PlanDetail> {
  return readJson<PlanDetail>(`/api/plans/${planId}/approve-stage2`, {
    method: "POST",
    token,
  });
}

export function approveAndResumeGeneration(
  token: string,
  planId: string,
  payload: ApproveAndResumeGenerationRequest,
): Promise<GenerationJobResponse> {
  return readJson<GenerationJobResponse>(`/api/admin/plans/${planId}/approve-and-resume-generation`, {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export function rejectApprovedPlan(token: string, planId: string): Promise<PlanDetail> {
  return readJson<PlanDetail>(`/api/admin/plans/${planId}/reject`, {
    method: "POST",
    token,
  });
}

export function archivePlan(token: string, planId: string): Promise<PlanDetail> {
  return readJson<PlanDetail>(`/api/admin/plans/${planId}/archive`, {
    method: "POST",
    token,
  });
}
