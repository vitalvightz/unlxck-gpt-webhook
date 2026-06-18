import type {
  ApproveAndResumeGenerationRequest,
  AdminAthleteDailyStatus,
  AdminAthleteRecord,
  AdminLatestIntakeUpdateRequest,
  AdminGenerationJobDiagnostic,
  AdminPlanSummary,
  AdminReviewRecord,
  AdminReviewResolveRequest,
  AthleteDashboardState,
  DailyCheckinRecord,
  DailyCheckinRequest,
  DailyCheckinResponse,
  InjuryFlagCreateRequest,
  InjuryFlagRecord,
  InjuryFlagStatus,
  ManualStage2SubmissionRequest,
  GenerationJobResponse,
  MeResponse,
  NutritionWorkspaceState,
  NutritionWorkspaceUpdateRequest,
  PlanDetail,
  PlanRequest,
  PlanSummary,
  ProfileUpdateRequest,
  SessionLogRecord,
  SessionLogRequest,
  SessionLogResponse,
  TodayCheckinRequest,
  TodayCheckinResponse,
  TodayCommandView,
  TodaySessionCompletionRequest,
  TodaySessionCompletionResponse,
  UsernameChangeRequest,
  WeeklySchedule,
} from "@/lib/types";

const EXPLICIT_API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? null;
const LOCAL_API_BASE_URL = "http://127.0.0.1:8000";
const DEFAULT_API_REQUEST_TIMEOUT_MS = 60_000;

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
  planSource?: string | null;
};

/**
 * Error thrown for non-2xx HTTP responses. Includes the HTTP `status` code and,
 * when the backend supplies one, a stable machine-readable `code` (e.g.
 * `generation_already_in_flight`). Prefer branching on `code` over matching the
 * human-readable `message`, which is free to change.
 */
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const RETRYABLE_GATEWAY_STATUSES = new Set([502, 503, 504]);
const RETRYABLE_INTERNAL_ERROR_SNIPPETS = [
  "failed to ensure profile",
  "profile service temporarily unavailable",
  "store service temporarily unavailable",
];
export const RETRYABLE_NETWORK_MESSAGE = "Connection issue. Try again in a minute.";
const meRequestsByToken = new Map<string, Promise<MeResponse>>();
const meUpdatesByToken = new Map<string, Promise<MeResponse>>();

function getApiRequestTimeoutMs(): number {
  const rawValue = process.env.NEXT_PUBLIC_API_REQUEST_TIMEOUT_MS?.trim();
  if (!rawValue) {
    return DEFAULT_API_REQUEST_TIMEOUT_MS;
  }
  const parsed = Number.parseInt(rawValue, 10);
  if (!Number.isFinite(parsed)) {
    return DEFAULT_API_REQUEST_TIMEOUT_MS;
  }
  return Math.max(0, parsed);
}

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
    if (RETRYABLE_GATEWAY_STATUSES.has(error.status)) {
      return true;
    }
    return (
      error.status >= 500 &&
      RETRYABLE_INTERNAL_ERROR_SNIPPETS.some((snippet) =>
        error.message.toLowerCase().includes(snippet),
      )
    );
  }
  return error instanceof Error && error.message === RETRYABLE_NETWORK_MESSAGE;
}

async function sleep(ms: number): Promise<void> {
  await new Promise((resolve) => globalThis.setTimeout(resolve, ms));
}

function createClientRequestId(prefix: string): string {
  const randomId =
    globalThis.crypto?.randomUUID?.() ??
    `${Date.now()}_${Math.random().toString(16).slice(2)}`;

  return `${prefix}_${randomId}`;
}

function shouldLogApiDetails(): boolean {
  // Detailed API logging can include raw response bodies, which may contain
  // athlete or plan data. Never enable it in production browser logs,
  // regardless of NEXT_PUBLIC_API_DEBUG.
  if (process.env.NODE_ENV === "production") {
    return false;
  }
  // Outside production, keep the existing local/dev debugging behaviour:
  // detailed logging is on by default. NEXT_PUBLIC_API_DEBUG can be set to
  // "false" to silence it locally.
  return process.env.NEXT_PUBLIC_API_DEBUG !== "false";
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

type ExecutedRequest = {
  response: Response;
  path: string;
  method: string;
  url: string;
  durationMs: number;
  contentType: string;
  requestId: string | null;
};

async function executeRequest(path: string, init?: ApiRequestInit): Promise<ExecutedRequest> {
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
  if (init?.planSource) {
    headers.set("X-Plan-Source", init.planSource);
  }

  const method = init?.method ?? "GET";
  const url = `${getApiBaseUrl()}${path}`;
  const startedAt = Date.now();
  const timeoutMs = getApiRequestTimeoutMs();
  const abortController = new AbortController();
  let timeoutId: ReturnType<typeof globalThis.setTimeout> | null = null;
  const abortFromCaller = () => abortController.abort();

  if (init?.signal?.aborted) {
    abortController.abort();
  } else {
    init?.signal?.addEventListener("abort", abortFromCaller, { once: true });
  }

  if (shouldLogApiDetails()) {
    console.info("[api] request:start", {
      path,
      method,
      url,
      hasBody: Boolean(init?.body),
      hasToken: Boolean(init?.token),
      startedAtIso: new Date(startedAt).toISOString(),
    });
  }

  let response: Response;
  try {
    if (timeoutMs > 0) {
      timeoutId = globalThis.setTimeout(() => abortController.abort(), timeoutMs);
    }
    response = await fetch(url, {
      ...init,
      cache: "no-store",
      headers,
      signal: abortController.signal,
    });
  } catch (networkError) {
    const durationMs = Date.now() - startedAt;
    if (shouldLogApiDetails()) {
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
    }
    throw new Error(RETRYABLE_NETWORK_MESSAGE, {
      cause: networkError,
    });
  } finally {
    if (timeoutId) {
      globalThis.clearTimeout(timeoutId);
    }
    init?.signal?.removeEventListener("abort", abortFromCaller);
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
        if (shouldLogApiDetails()) {
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
    }

    if (shouldLogApiDetails()) {
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
    }

    if (parsedBody && typeof parsedBody === "object" && parsedBody !== null) {
      const detail = "detail" in parsedBody ? (parsedBody as { detail?: unknown }).detail : null;
      const bodyRequestId =
        "request_id" in parsedBody ? (parsedBody as { request_id?: unknown }).request_id : null;
      const rawCode = "code" in parsedBody ? (parsedBody as { code?: unknown }).code : null;
      const errorCode = typeof rawCode === "string" && rawCode ? rawCode : undefined;

      if (typeof detail === "string") {
        throw new ApiError(
          bodyRequestId ? `${detail} (request id: ${String(bodyRequestId)})` : detail,
          response.status,
          errorCode,
        );
      }

      if (detail != null) {
        throw new ApiError(
          bodyRequestId
            ? `${JSON.stringify(detail)} (request id: ${String(bodyRequestId)})`
            : JSON.stringify(detail),
          response.status,
          errorCode,
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

  return { response, path, method, url, durationMs, contentType, requestId };
}

async function readJson<T>(path: string, init?: ApiRequestInit): Promise<T> {
  const { response, method, url, durationMs, contentType, requestId } = await executeRequest(
    path,
    init,
  );

  try {
    const data = (await response.json()) as T;
    if (shouldLogApiDetails()) {
      console.info("[api] request:success", {
        path,
        method,
        url,
        requestId,
        status: response.status,
        durationMs,
      });
    }
    return data;
  } catch (parseError) {
    if (shouldLogApiDetails()) {
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
    }
    throw new Error("Server returned an unreadable response.");
  }
}

async function requestVoid(path: string, init?: ApiRequestInit): Promise<void> {
  const { response, method, url, durationMs, requestId } = await executeRequest(path, init);

  // Drain the body so the connection can be released even when the server
  // returned content alongside a 200/204. We do not parse or throw on body
  // content here — success status is the contract for void requests.
  if (response.status !== 204) {
    try {
      await response.text();
    } catch {
      // Ignore — the server may have already closed the stream.
    }
  }

  if (shouldLogApiDetails()) {
    console.info("[api] request:success", {
      path,
      method,
      url,
      requestId,
      status: response.status,
      durationMs,
    });
  }
}

export function getMe(token: string): Promise<MeResponse> {
  const activeUpdate = meUpdatesByToken.get(token);
  if (activeUpdate) {
    return activeUpdate;
  }

  const activeRequest = meRequestsByToken.get(token);
  if (activeRequest) {
    return activeRequest;
  }

  const request = readJson<MeResponse>("/api/me", { token }).finally(() => {
    if (meRequestsByToken.get(token) === request) {
      meRequestsByToken.delete(token);
    }
  });
  meRequestsByToken.set(token, request);
  return request;
}

export function updateMe(token: string, payload: ProfileUpdateRequest): Promise<MeResponse> {
  meRequestsByToken.delete(token);
  const request = readJson<MeResponse>("/api/me", {
    method: "PUT",
    token,
    body: JSON.stringify(payload),
  }).finally(() => {
    if (meUpdatesByToken.get(token) === request) {
      meUpdatesByToken.delete(token);
    }
    meRequestsByToken.delete(token);
  });
  meUpdatesByToken.set(token, request);
  return request;
}

export function changeUsername(token: string, payload: UsernameChangeRequest): Promise<MeResponse> {
  meRequestsByToken.delete(token);
  const request = readJson<MeResponse>("/api/me/username", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  }).finally(() => {
    if (meUpdatesByToken.get(token) === request) {
      meUpdatesByToken.delete(token);
    }
    meRequestsByToken.delete(token);
  });
  meUpdatesByToken.set(token, request);
  return request;
}

export function saveOnboardingDraft(
  token: string,
  payload: Pick<
    ProfileUpdateRequest,
    "onboarding_draft" | "full_name" | "technical_style" | "tactical_style" | "stance" | "professional_status" | "record" | "athlete_timezone"
  >,
): Promise<{ ok: boolean; updated_at: string }> {
  return readJson<{ ok: boolean; updated_at: string }>("/api/onboarding/draft", {
    method: "PATCH",
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
  planSource?: string | null,
): Promise<GenerationJobResponse> {
  const stableClientRequestId = clientRequestId ?? createClientRequestId("plan_generate");

  return withTransientRetries(() =>
    readJson<GenerationJobResponse>("/api/plans/generate", {
      method: "POST",
      token,
      clientRequestId: stableClientRequestId,
      planSource,
      body: JSON.stringify(payload),
    }),
  );
}

export function getGenerationJob(token: string, jobId: string): Promise<GenerationJobResponse> {
  return withTransientRetries(() =>
    readJson<GenerationJobResponse>(`/api/generation-jobs/${encodeURIComponent(jobId)}`, { token }),
  );
}

export function getActiveGenerationJob(token: string): Promise<GenerationJobResponse | null> {
  return withTransientRetries(() =>
    readJson<GenerationJobResponse | null>("/api/generation-jobs/active", { token }),
  );
}

export function getLatestGenerationJob(token: string): Promise<GenerationJobResponse | null> {
  return withTransientRetries(() =>
    readJson<GenerationJobResponse | null>("/api/generation-jobs/latest", { token }),
  );
}

export function retryGenerationJob(
  token: string,
  jobId: string,
  clientRequestId?: string,
): Promise<GenerationJobResponse> {
  const stableClientRequestId = clientRequestId ?? createClientRequestId(`retry_${jobId}`);

  return withTransientRetries(() =>
    readJson<GenerationJobResponse>(`/api/generation-jobs/${encodeURIComponent(jobId)}/retry`, {
      method: "POST",
      token,
      clientRequestId: stableClientRequestId,
    }),
  );
}

export function listPlans(token: string): Promise<PlanSummary[]> {
  return withTransientRetries(() => readJson<PlanSummary[]>("/api/plans", { token }));
}

export function getPlan(token: string, planId: string): Promise<PlanDetail> {
  return withTransientRetries(() =>
    readJson<PlanDetail>(`/api/plans/${encodeURIComponent(planId)}`, { token }),
  );
}

export async function fetchWeeklySchedule(
  planId: string,
  weekIndex = 0,
  token?: string | null,
): Promise<WeeklySchedule | null> {
  try {
    return await readJson<WeeklySchedule>(
      `/api/plans/${encodeURIComponent(planId)}/weekly-schedule?week_index=${weekIndex}`,
      { token },
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
}

export function renamePlan(token: string, planId: string, planName: string): Promise<PlanDetail> {
  return withTransientRetries(() =>
    readJson<PlanDetail>(`/api/plans/${encodeURIComponent(planId)}`, {
      method: "PATCH",
      token,
      body: JSON.stringify({ plan_name: planName }),
    }),
  );
}

// Archives the plan (soft delete). The server-side DELETE route is archive-only;
// the plan stays recoverable in the athlete's archived list.
export async function deletePlan(token: string, planId: string): Promise<void> {
  return withTransientRetries(() =>
    requestVoid(`/api/plans/${encodeURIComponent(planId)}`, {
      method: "DELETE",
      token,
    }),
  );
}

// Admin-only hard delete. Requires the exact plan name as typed confirmation.
export async function permanentlyDeletePlan(
  token: string,
  planId: string,
  confirmPlanName: string,
): Promise<void> {
  return requestVoid(`/api/admin/plans/${encodeURIComponent(planId)}/permanent`, {
    method: "DELETE",
    token,
    body: JSON.stringify({ confirm_plan_name: confirmPlanName }),
  });
}

export type AdminListQuery = {
  q?: string;
  limit?: number;
  offset?: number;
};

function buildAdminListPath(basePath: string, query?: AdminListQuery): string {
  const params = new URLSearchParams();
  const trimmedQuery = query?.q?.trim();
  if (trimmedQuery) {
    params.set("q", trimmedQuery);
  }
  if (typeof query?.limit === "number") {
    params.set("limit", String(query.limit));
  }
  if (typeof query?.offset === "number") {
    params.set("offset", String(query.offset));
  }
  const search = params.toString();
  return search ? `${basePath}?${search}` : basePath;
}

export function listAdminAthletes(
  token: string,
  query?: AdminListQuery,
): Promise<AdminAthleteRecord[]> {
  return withTransientRetries(() =>
    readJson<AdminAthleteRecord[]>(buildAdminListPath("/api/admin/athletes", query), { token }),
  );
}

export function getAdminAthlete(token: string, athleteId: string): Promise<AdminAthleteRecord> {
  return withTransientRetries(() =>
    readJson<AdminAthleteRecord>(`/api/admin/athletes/${encodeURIComponent(athleteId)}`, { token }),
  );
}

export function updateAdminAthleteLatestIntake(
  token: string,
  athleteId: string,
  payload: AdminLatestIntakeUpdateRequest,
): Promise<AdminAthleteRecord> {
  return withTransientRetries(() =>
    readJson<AdminAthleteRecord>(`/api/admin/athletes/${encodeURIComponent(athleteId)}/latest-intake`, {
      method: "PATCH",
      token,
      body: JSON.stringify(payload),
    }),
  );
}

export function getAdminAthleteNutritionCurrent(
  token: string,
  athleteId: string,
): Promise<NutritionWorkspaceState> {
  return withTransientRetries(() =>
    readJson<NutritionWorkspaceState>(`/api/admin/athletes/${encodeURIComponent(athleteId)}/nutrition/current`, { token }),
  );
}

export function updateAdminAthleteNutritionCurrent(
  token: string,
  athleteId: string,
  payload: NutritionWorkspaceUpdateRequest,
): Promise<NutritionWorkspaceState> {
  return withTransientRetries(() =>
    readJson<NutritionWorkspaceState>(`/api/admin/athletes/${encodeURIComponent(athleteId)}/nutrition/current`, {
      method: "PUT",
      token,
      body: JSON.stringify(payload),
    }),
  );
}

export function generateAdminAthletePlanFromLatestIntake(
  token: string,
  athleteId: string,
  clientRequestId?: string,
): Promise<GenerationJobResponse> {
  const stableClientRequestId =
    clientRequestId ?? createClientRequestId(`admin_latest_intake_${athleteId}`);

  return withTransientRetries(() =>
    readJson<GenerationJobResponse>(
      `/api/admin/athletes/${encodeURIComponent(athleteId)}/plans/generate-from-latest-intake`,
      {
        method: "POST",
        token,
        clientRequestId: stableClientRequestId,
      },
    ),
  );
}

export function getAdminAthleteGenerationJobs(
  token: string,
  athleteId: string,
  limit = 10,
): Promise<AdminGenerationJobDiagnostic[]> {
  return withTransientRetries(() =>
    readJson<AdminGenerationJobDiagnostic[]>(
      `/api/admin/athletes/${encodeURIComponent(athleteId)}/generation-jobs?limit=${limit}`,
      { token },
    ),
  );
}

export function listAdminTriageGenerationJobs(
  token: string,
  limit = 50,
): Promise<AdminGenerationJobDiagnostic[]> {
  return withTransientRetries(() =>
    readJson<AdminGenerationJobDiagnostic[]>(
      `/api/admin/generation-jobs/triage?limit=${limit}`,
      { token },
    ),
  );
}

export function listAdminActiveGenerationJobs(
  token: string,
  limit = 50,
): Promise<AdminGenerationJobDiagnostic[]> {
  return withTransientRetries(() =>
    readJson<AdminGenerationJobDiagnostic[]>(
      `/api/admin/generation-jobs/active?limit=${limit}`,
      { token },
    ),
  );
}

export function listAdminPlans(
  token: string,
  query?: AdminListQuery,
): Promise<AdminPlanSummary[]> {
  return withTransientRetries(() =>
    readJson<AdminPlanSummary[]>(buildAdminListPath("/api/admin/plans", query), { token }),
  );
}

export function listAdminReviewPlans(
  token: string,
  limit = 100,
): Promise<AdminPlanSummary[]> {
  return withTransientRetries(() =>
    readJson<AdminPlanSummary[]>(`/api/admin/plans/review?limit=${limit}`, { token }),
  );
}

export function submitManualStage2(
  token: string,
  planId: string,
  payload: ManualStage2SubmissionRequest,
): Promise<PlanDetail> {
  return readJson<PlanDetail>(`/api/admin/plans/${encodeURIComponent(planId)}/manual-stage2`, {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export function approvePlanForRelease(token: string, planId: string): Promise<PlanDetail> {
  return readJson<PlanDetail>(`/api/admin/plans/${encodeURIComponent(planId)}/approve`, {
    method: "POST",
    token,
  });
}

export function approveAndResumeGeneration(
  token: string,
  planId: string,
  payload: ApproveAndResumeGenerationRequest,
  clientRequestId?: string,
): Promise<GenerationJobResponse> {
  const stableClientRequestId = clientRequestId ?? createClientRequestId(`triage_resume_${planId}`);

  return withTransientRetries(() =>
    readJson<GenerationJobResponse>(
      `/api/admin/plans/${encodeURIComponent(planId)}/approve-and-resume-generation`,
      {
        method: "POST",
        token,
        clientRequestId: stableClientRequestId,
        body: JSON.stringify(payload),
      },
    ),
  );
}

export function approveAndResumeGenerationFromJob(
  token: string,
  jobId: string,
  payload: ApproveAndResumeGenerationRequest,
  clientRequestId?: string,
): Promise<GenerationJobResponse> {
  const stableClientRequestId = clientRequestId ?? createClientRequestId(`triage_resume_job_${jobId}`);

  return withTransientRetries(() =>
    readJson<GenerationJobResponse>(
      `/api/admin/generation-jobs/${encodeURIComponent(jobId)}/approve-and-resume-generation`,
      {
        method: "POST",
        token,
        clientRequestId: stableClientRequestId,
        body: JSON.stringify(payload),
      },
    ),
  );
}

export function rejectApprovedPlan(token: string, planId: string): Promise<PlanDetail> {
  return readJson<PlanDetail>(`/api/admin/plans/${encodeURIComponent(planId)}/reject`, {
    method: "POST",
    token,
  });
}

export function archivePlan(token: string, planId: string): Promise<PlanDetail> {
  return readJson<PlanDetail>(`/api/admin/plans/${encodeURIComponent(planId)}/archive`, {
    method: "POST",
    token,
  });
}

export type StructuredPlanBackfillResult = {
  queued: number;
  plan_ids: string[];
};

/**
 * Trigger a background backfill that re-runs structured-plan conversion for
 * athlete-displayable plans that have no structured card yet (legacy plans
 * generated before structured generation existed). Returns immediately with the
 * queued plan ids; cards appear on each plan as its conversion lands.
 */
export function backfillStructuredPlans(
  token: string,
  options?: { limit?: number },
): Promise<StructuredPlanBackfillResult> {
  const query =
    typeof options?.limit === "number" ? `?limit=${encodeURIComponent(options.limit)}` : "";
  return readJson<StructuredPlanBackfillResult>(
    `/api/admin/plans/structured-plan/backfill${query}`,
    {
      method: "POST",
      token,
    },
  );
}

// ---------------------------------------------------------------------------
// Live athlete daily flow (dashboard, check-ins, session logs, injury flags,
// admin review queue).
// ---------------------------------------------------------------------------

export function getDashboard(token: string): Promise<AthleteDashboardState> {
  return withTransientRetries(() => readJson<AthleteDashboardState>("/api/dashboard", { token }));
}

export function submitDailyCheckin(
  token: string,
  payload: DailyCheckinRequest,
): Promise<DailyCheckinResponse> {
  return readJson<DailyCheckinResponse>("/api/checkins", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export function listDailyCheckins(token: string, limit = 14): Promise<DailyCheckinRecord[]> {
  return withTransientRetries(() =>
    readJson<DailyCheckinRecord[]>(`/api/checkins?limit=${limit}`, { token }),
  );
}

export function submitSessionLog(
  token: string,
  payload: SessionLogRequest,
): Promise<SessionLogResponse> {
  return readJson<SessionLogResponse>("/api/session-logs", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export function listSessionLogs(token: string, limit = 20): Promise<SessionLogRecord[]> {
  return withTransientRetries(() =>
    readJson<SessionLogRecord[]>(`/api/session-logs?limit=${limit}`, { token }),
  );
}

export function reportInjury(
  token: string,
  payload: InjuryFlagCreateRequest,
): Promise<InjuryFlagRecord> {
  return readJson<InjuryFlagRecord>("/api/injury-flags", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export function listInjuryFlags(token: string, includeResolved = false): Promise<InjuryFlagRecord[]> {
  return withTransientRetries(() =>
    readJson<InjuryFlagRecord[]>(`/api/injury-flags?include_resolved=${includeResolved}`, { token }),
  );
}

export function listAdminReviews(
  token: string,
  status: AdminReviewRecord["status"] | "all" = "pending",
  limit = 50,
): Promise<AdminReviewRecord[]> {
  return withTransientRetries(() =>
    readJson<AdminReviewRecord[]>(
      `/api/admin/reviews?status=${encodeURIComponent(status)}&limit=${limit}`,
      { token },
    ),
  );
}

export function resolveAdminReview(
  token: string,
  reviewId: string,
  payload: AdminReviewResolveRequest,
): Promise<AdminReviewRecord> {
  return readJson<AdminReviewRecord>(
    `/api/admin/reviews/${encodeURIComponent(reviewId)}/resolve`,
    {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    },
  );
}

export function updateAdminInjuryFlag(
  token: string,
  flagId: string,
  status: InjuryFlagStatus,
): Promise<InjuryFlagRecord> {
  return readJson<InjuryFlagRecord>(`/api/admin/injury-flags/${encodeURIComponent(flagId)}`, {
    method: "PATCH",
    token,
    body: JSON.stringify({ status }),
  });
}

export function getAdminAthleteDailyStatus(
  token: string,
  athleteId: string,
): Promise<AdminAthleteDailyStatus> {
  return withTransientRetries(() =>
    readJson<AdminAthleteDailyStatus>(
      `/api/admin/athletes/${encodeURIComponent(athleteId)}/daily-status`,
      { token },
    ),
  );
}

export function getToday(token: string): Promise<TodayCommandView> {
  return withTransientRetries(() => readJson<TodayCommandView>("/api/today", { token }));
}

export function submitTodayCheckin(
  token: string,
  payload: TodayCheckinRequest,
): Promise<TodayCheckinResponse> {
  return readJson<TodayCheckinResponse>("/api/today/checkin", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export function submitTodaySessionCompletion(
  token: string,
  payload: TodaySessionCompletionRequest,
): Promise<TodaySessionCompletionResponse> {
  return readJson<TodaySessionCompletionResponse>("/api/today/session-completion", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}
