"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, getGenerationJob, isRetryableApiFailure, retryGenerationJob } from "@/lib/api";
import {
  classifyGenerationFailure,
  isRetryableGenerationFailure,
  STALLED_GENERATION_ERROR,
  type GenerationFailureKind,
} from "@/lib/generation-failure";
import { normalizeLegacyGenerationJobStatus } from "@/lib/generation-status-guards";
import type { GenerationJobResponse, GenerationJobStatus, ProgressMilestone } from "@/lib/types";

export type GenerationUiPhase =
  | "submitting"
  | "queued"
  | "running"
  | "reconnecting"
  | "finalizing"
  | "already_generated"
  | "review_paused"
  | "failed";

type PendingGenerationState = {
  clientRequestId: string;
  jobId?: string | null;
  createdAt: string;
};

type RecoverablePendingGenerationState = PendingGenerationState & { jobId: string };

export function canRecoverPendingGenerationWithoutCreate(
  pending: PendingGenerationState | null,
): pending is RecoverablePendingGenerationState {
  return typeof pending?.jobId === "string" && pending.jobId.length > 0;
}

export function resolveFailedJobWithSavedPlan(job: GenerationJobResponse): string | null {
  if (normalizeLegacyGenerationJobStatus(job.status) !== "failed") {
    return null;
  }
  return job.plan_id || job.latest_plan_id || null;
}
export function resolveTerminalJobPlanId(job: GenerationJobResponse): string | null {
  return job.plan_id || job.latest_plan_id || null;
}

export type CompletedTerminalJobOutcome =
  | { type: "open"; planId: string }
  | { type: "review_paused" }
  | { type: "already_generated" };

export function resolveCompletedTerminalJobOutcome(job: GenerationJobResponse): CompletedTerminalJobOutcome {
  const planId = resolveTerminalJobPlanId(job);
  if (planId && planId.trim()) {
    return { type: "open", planId: planId.trim() };
  }
  // Triage outcomes live on the job (no plan_id). The UI must stop polling
  // and surface admin-review copy instead of "already generated".
  if (job.requires_admin_resume === true) {
    return { type: "review_paused" };
  }
  return { type: "already_generated" };
}

type GenerationCompletion = {
  // Null when the outcome is a protected triage hold — no plan row exists.
  planId: string | null;
  status: Extract<GenerationJobStatus, "completed" | "review_required">;
  recovered: boolean;
  requiresAdminResume?: boolean;
  stage2Status?: string | null;
};

type GenerationControllerOptions = {
  token: string | null;
  storageKey: string | null;
  createJob: (clientRequestId: string) => Promise<GenerationJobResponse>;
  onComplete: (result: GenerationCompletion) => void;
  // Optional fallback used when the backend reports an existing in-flight job
  // for the same athlete (typical when the user submitted from another tab or
  // device). If provided and createJob raises that conflict, the controller
  // attaches to the returned active job instead of surfacing a raw 409.
  recoverActiveJob?: () => Promise<GenerationJobResponse | null>;
};

// Stable machine-readable code the backend attaches to the 409 raised when
// another tab/device beat us to the active-job slot. Branching on the code
// keeps recovery working even if the human-readable copy is reworded.
const GENERATION_ALREADY_IN_FLIGHT_CODE = "generation_already_in_flight";
// Legacy fallback: older backends (and any response that loses the code field)
// only carry the detail string, surfaced verbatim through ApiError.message.
const GENERATION_ALREADY_IN_FLIGHT_ERROR_SNIPPET =
  "A generation job is already queued or running for this account.";

export function isGenerationAlreadyInFlightError(error: unknown): boolean {
  if (error instanceof ApiError && error.code === GENERATION_ALREADY_IN_FLIGHT_CODE) {
    return true;
  }
  if (!(error instanceof Error)) {
    return false;
  }
  return error.message.includes(GENERATION_ALREADY_IN_FLIGHT_ERROR_SNIPPET);
}

type StartGenerationOptions = {
  clientRequestId?: string;
  recovered?: boolean;
  existingJob?: GenerationJobResponse;
};

const INITIAL_POLL_MS = 2_000;
const MEDIUM_POLL_MS = 5_000;
const LONG_POLL_MS = 15_000;
const PRE_START_STALE_MS = 90_000;
const PENDING_GENERATION_PREFIX = "unlxck:pending-generation:";
const TRAINING_AVAILABILITY_MISMATCH_ERROR =
  "invalid Weekly Training Frequency: cannot exceed selected Training Availability days";
const TRAINING_AVAILABILITY_MISMATCH_UI_MESSAGE =
  "You selected fewer available training days than your weekly training frequency. Either reduce Weekly Training Frequency or select more Training Availability days.";

function mapGenerationErrorMessage(error: unknown): string {
  if (!(error instanceof Error)) {
    return "Unable to generate your plan.";
  }
  if (error.message.includes(TRAINING_AVAILABILITY_MISMATCH_ERROR)) {
    return TRAINING_AVAILABILITY_MISMATCH_UI_MESSAGE;
  }
  return error.message;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function buildClientRequestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `gen_${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function getPendingGeneration(storageKey: string | null): PendingGenerationState | null {
  if (!storageKey || typeof window === "undefined") {
    return null;
  }
  const raw = window.localStorage.getItem(storageKey);
  if (!raw) {
    return null;
  }
  try {
    const decoded = JSON.parse(raw) as PendingGenerationState;
    return decoded?.clientRequestId ? decoded : null;
  } catch {
    window.localStorage.removeItem(storageKey);
    return null;
  }
}

function clearOtherPendingGenerations(activeStorageKey: string | null): void {
  if (typeof window === "undefined") {
    return;
  }

  Object.keys(window.localStorage)
    .filter((key) => key.startsWith(PENDING_GENERATION_PREFIX) && key !== activeStorageKey)
    .forEach((key) => window.localStorage.removeItem(key));
}

function clearAllPendingGenerations(): void {
  if (typeof window === "undefined") {
    return;
  }

  Object.keys(window.localStorage)
    .filter((key) => key.startsWith(PENDING_GENERATION_PREFIX))
    .forEach((key) => window.localStorage.removeItem(key));
}

function savePendingGeneration(storageKey: string | null, pending: PendingGenerationState): void {
  if (!storageKey || typeof window === "undefined") {
    return;
  }
  clearOtherPendingGenerations(storageKey);
  window.localStorage.setItem(storageKey, JSON.stringify(pending));
}

function clearPendingGeneration(storageKey: string | null): void {
  if (!storageKey || typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(storageKey);
}

function getPollDelay(startedAtMs: number): number {
  const elapsedMs = Date.now() - startedAtMs;
  if (elapsedMs < 60_000) {
    return INITIAL_POLL_MS;
  }
  if (elapsedMs < 5 * 60_000) {
    return MEDIUM_POLL_MS;
  }
  return LONG_POLL_MS;
}

function statusMessageForJob(status: GenerationJobStatus, startedAtMs: number): string {
  const elapsedMinutes = Math.floor((Date.now() - startedAtMs) / 60_000);
  const suffix =
    elapsedMinutes >= 5
      ? " This is safe to leave and return to; we will reconnect when you come back."
      : "";

  if (status === "queued") {
    return `Your saved intake is queued for planning.${suffix}`;
  }
  if (status === "running") {
    return `Your fight-camp plan is being built.${suffix}`;
  }
  return "Finalizing your plan.";
}

function phaseForJobStatus(status: GenerationJobStatus): Exclude<GenerationUiPhase, "submitting" | "reconnecting" | "already_generated" | "failed"> {
  if (status === "queued") {
    return "queued";
  }
  if (status === "running") {
    return "running";
  }
  return "finalizing";
}

export function isPreStartStaleGenerationJob(job: GenerationJobResponse, nowMs = Date.now()): boolean {
  if (job.status !== "running") {
    return false;
  }
  if (Array.isArray(job.progress_milestones) && job.progress_milestones.length > 0) {
    return false;
  }
  const heartbeatAtMs = Date.parse(job.heartbeat_at || "");
  const startedAtMs = Date.parse(job.started_at || "");
  const hasHeartbeat = Number.isFinite(heartbeatAtMs);
  const hasStartedAt = Number.isFinite(startedAtMs);
  if (hasHeartbeat && hasStartedAt && heartbeatAtMs <= startedAtMs) {
    return true;
  }
  const lastProgressAtMs = hasHeartbeat ? heartbeatAtMs : startedAtMs;
  return Number.isFinite(lastProgressAtMs) && nowMs - lastProgressAtMs >= PRE_START_STALE_MS;
}

async function createJobWithReconnect(
  createJob: (clientRequestId: string) => Promise<GenerationJobResponse>,
  clientRequestId: string,
  setStatusMessage: (message: string | null) => void,
  setPhase: (phase: GenerationUiPhase) => void,
  recoverActiveJob?: () => Promise<GenerationJobResponse | null>,
): Promise<GenerationJobResponse> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      return await createJob(clientRequestId);
    } catch (error) {
      lastError = error;
      if (isGenerationAlreadyInFlightError(error) && recoverActiveJob) {
        // Another tab/device already started a job for this athlete. Rather
        // than surfacing a raw 409, attach to the in-flight job so the UI
        // shows the live build instead of a confusing "create failed" state.
        try {
          const activeJob = await recoverActiveJob();
          if (activeJob) {
            setPhase("reconnecting");
            setStatusMessage(
              "Reconnecting to a plan build already in progress on another tab or device.",
            );
            return activeJob;
          }
        } catch {
          // Active lookup unavailable; fall through to the original error.
        }
        throw error;
      }
      if (!isRetryableApiFailure(error)) {
        throw error;
      }
      if (attempt === 3) {
        break;
      }
      setPhase("reconnecting");
      setStatusMessage("Connection dropped while starting the job. Reconnecting to the same request.");
      await sleep(1_500 * attempt);
    }
  }
  throw lastError instanceof Error ? lastError : new Error("Unable to start plan generation.");
}

export function useGenerationController({
  token,
  storageKey,
  createJob,
  onComplete,
  recoverActiveJob,
}: GenerationControllerOptions) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [phase, setPhase] = useState<GenerationUiPhase>(() =>
    getPendingGeneration(storageKey) ? "reconnecting" : "submitting",
  );
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [milestones, setMilestones] = useState<ProgressMilestone[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [failedJobId, setFailedJobId] = useState<string | null>(null);
  const [failureKind, setFailureKind] = useState<GenerationFailureKind | null>(null);
  // State updates are not visible to the async function that just scheduled
  // them, and the failure classifier has to know synchronously whether a job
  // was ever created — so the job id is mirrored into a ref.
  const failedJobIdRef = useRef<string | null>(null);

  const markFailedJob = useCallback((jobId: string | null) => {
    failedJobIdRef.current = jobId;
    setFailedJobId(jobId);
  }, []);

  const recordFailure = useCallback((generationError: unknown) => {
    const kind = classifyGenerationFailure(generationError, {
      hasFailedJobId: Boolean(failedJobIdRef.current),
    });
    setPhase("failed");
    setStatusMessage(null);
    setIsGenerating(false);
    setFailureKind(kind);
    setError(mapGenerationErrorMessage(generationError));
  }, []);

  const [startedAtMs, setStartedAtMs] = useState<number | null>(() => {
    const pending = getPendingGeneration(storageKey);
    if (!pending) {
      return null;
    }
    const parsed = Date.parse(pending.createdAt || "");
    return Number.isFinite(parsed) ? parsed : null;
  });
  const recoveryAttemptedRef = useRef<string | null>(null);

  const watchJobUntilTerminal = useCallback(
    async (
      activeToken: string,
      activeStorageKey: string,
      job: GenerationJobResponse,
      clientRequestId: string,
      pendingCreatedAtFallback: string,
      createdAtMs: number,
      recovered: boolean,
    ) => {
      setPhase(phaseForJobStatus(job.status));
      setStatusMessage(statusMessageForJob(job.status, createdAtMs));
      if (Array.isArray(job.progress_milestones)) {
        setMilestones(job.progress_milestones);
      }
      if (isPreStartStaleGenerationJob(job)) {
        clearAllPendingGenerations();
        markFailedJob(job.job_id);
        throw new Error(STALLED_GENERATION_ERROR);
      }
      savePendingGeneration(activeStorageKey, {
        clientRequestId,
        jobId: job.job_id,
        createdAt: job.created_at || pendingCreatedAtFallback,
      });

      for (;;) {
        const currentJob = await getGenerationJob(activeToken, job.job_id);

        if (Array.isArray(currentJob.progress_milestones)) {
          setMilestones(currentJob.progress_milestones);
        }

        if (isPreStartStaleGenerationJob(currentJob)) {
          clearAllPendingGenerations();
          markFailedJob(currentJob.job_id);
          throw new Error(STALLED_GENERATION_ERROR);
        }

        savePendingGeneration(activeStorageKey, {
          clientRequestId,
          jobId: currentJob.job_id,
          createdAt: currentJob.created_at || pendingCreatedAtFallback,
        });

        const normalizedStatus = normalizeLegacyGenerationJobStatus(currentJob.status);
        if (normalizedStatus === "completed" || normalizedStatus === "review_required") {
          const outcome = resolveCompletedTerminalJobOutcome(currentJob);
          if (outcome.type === "already_generated") {
            clearAllPendingGenerations();
            setPhase("already_generated");
            setStatusMessage("This intake already has a generated plan.");
            setIsGenerating(false);
            return;
          }
          if (outcome.type === "review_paused") {
            // Triage-blocked outcome: no plan row. Stop polling, halt the
            // elapsed timer, and surface admin-review copy. onComplete is
            // invoked without a planId so the generate page won't redirect
            // to /plans/{id}.
            clearAllPendingGenerations();
            setPhase("review_paused");
            setStatusMessage(
              "Planning paused. Admin review is required before generation can continue.",
            );
            setIsGenerating(false);
            onComplete({
              planId: null,
              status: normalizedStatus,
              recovered,
              requiresAdminResume: true,
              stage2Status: currentJob.stage2_status ?? null,
            });
            return;
          }
          clearAllPendingGenerations();
          setPhase("finalizing");
          setStatusMessage("Final checks passed. Opening your saved plan.");
          setIsGenerating(false);
          await sleep(220);
          onComplete({
            planId: outcome.planId,
            status: normalizedStatus,
            recovered,
            requiresAdminResume: currentJob.requires_admin_resume === true,
            stage2Status: currentJob.stage2_status ?? null,
          });
          return;
        }

        if (normalizedStatus === "failed") {
          const recoveredPlanId = resolveFailedJobWithSavedPlan(currentJob);
          if (recoveredPlanId) {
            clearAllPendingGenerations();
            setPhase("finalizing");
            setStatusMessage("Opening your saved plan.");
            setIsGenerating(false);
            onComplete({
              planId: recoveredPlanId,
              status: "completed",
              recovered: true,
            });
            return;
          }
          clearAllPendingGenerations();
          markFailedJob(currentJob.job_id);
          throw new Error(currentJob.error || "Plan generation failed.");
        }

        const liveStatus: GenerationJobStatus = normalizedStatus === "queued" || normalizedStatus === "running"
          ? normalizedStatus
          : "running";
        setPhase(phaseForJobStatus(liveStatus));
        setStatusMessage(statusMessageForJob(liveStatus, createdAtMs));
        await sleep(getPollDelay(createdAtMs));
      }
    },
    [markFailedJob, onComplete],
  );

  const startGeneration = useCallback(
    async (options: StartGenerationOptions = {}) => {
      if (!token || !storageKey || isGenerating) {
        return;
      }

      setError(null);
      setFailureKind(null);
      markFailedJob(null);
      setIsGenerating(true);
      const recovered = options.recovered ?? false;
      const clientRequestId = options.clientRequestId ?? buildClientRequestId();
      const pendingCreatedAt = new Date().toISOString();
      const pendingCreatedAtMs = Date.parse(pendingCreatedAt) || Date.now();
      savePendingGeneration(storageKey, {
        clientRequestId,
        createdAt: pendingCreatedAt,
      });
      setStartedAtMs(pendingCreatedAtMs);

      try {
        setPhase(recovered ? "reconnecting" : "submitting");
        setStatusMessage(
          recovered
            ? "Reconnecting to your existing plan generation request."
            : "Submitting your plan generation request.",
        );
        setMilestones([]);
        const activeJob = options.existingJob
          ?? await createJobWithReconnect(
            createJob,
            clientRequestId,
            setStatusMessage,
            setPhase,
            recoverActiveJob,
          );
        const createdAtMs = Date.parse(activeJob.created_at || pendingCreatedAt) || Date.now();
        setStartedAtMs(createdAtMs);
        await watchJobUntilTerminal(
          token,
          storageKey,
          activeJob,
          clientRequestId,
          pendingCreatedAt,
          createdAtMs,
          recovered,
        );
      } catch (generationError) {
        clearPendingGeneration(storageKey);
        recordFailure(generationError);
      }
    },
    [createJob, isGenerating, markFailedJob, recordFailure, recoverActiveJob, storageKey, token, watchJobUntilTerminal],
  );

  const retryGeneration = useCallback(async () => {
    if (!token || !storageKey || isGenerating) {
      return;
    }

    // Nothing was created server-side (the request never landed), so there is
    // no job to re-run — start a fresh build instead of leaving the user on a
    // failure screen with a button that cannot do anything.
    if (!failedJobId) {
      setFailureKind(null);
      await startGeneration();
      return;
    }

    setError(null);
    setFailureKind(null);
    setIsGenerating(true);
    setMilestones([]);
    setPhase("submitting");
    setStatusMessage("Retrying your plan generation request.");

    const retryStartedAt = new Date().toISOString();
    const retryStartedAtMs = Date.parse(retryStartedAt) || Date.now();
    setStartedAtMs(retryStartedAtMs);

    try {
      const newJob = await retryGenerationJob(token, failedJobId);
      const clientRequestId = newJob.client_request_id || buildClientRequestId();
      const createdAtMs = Date.parse(newJob.created_at || retryStartedAt) || retryStartedAtMs;
      setStartedAtMs(createdAtMs);
      markFailedJob(null);
      await watchJobUntilTerminal(
        token,
        storageKey,
        newJob,
        clientRequestId,
        retryStartedAt,
        createdAtMs,
        false,
      );
    } catch (retryError) {
      clearPendingGeneration(storageKey);
      recordFailure(retryError);
    }
  }, [failedJobId, isGenerating, markFailedJob, recordFailure, startGeneration, storageKey, token, watchJobUntilTerminal]);

  useEffect(() => {
  if (!token || !storageKey || isGenerating) {
    return;
  }

  const pending = getPendingGeneration(storageKey);
  if (!canRecoverPendingGenerationWithoutCreate(pending)) {
    if (pending && !pending.jobId) {
      clearPendingGeneration(storageKey);
    }
    return;
  }

  const recoverablePending = pending;
  if (recoveryAttemptedRef.current === recoverablePending.clientRequestId) {
    return;
  }

  recoveryAttemptedRef.current = recoverablePending.clientRequestId;

  void (async () => {
    try {
      const existingJob = await getGenerationJob(token, recoverablePending.jobId);
      const normalizedStatus = normalizeLegacyGenerationJobStatus(existingJob.status);
      const failedJobSavedPlanId = resolveFailedJobWithSavedPlan(existingJob);

      if (
        normalizedStatus === "queued" ||
        normalizedStatus === "running" ||
        normalizedStatus === "completed" ||
        normalizedStatus === "review_required" ||
        failedJobSavedPlanId
      ) {
        await startGeneration({
          clientRequestId: recoverablePending.clientRequestId,
          recovered: true,
          existingJob,
        });
        return;
      }

      clearPendingGeneration(storageKey);
    } catch {
      clearPendingGeneration(storageKey);
    }
  })();
}, [isGenerating, startGeneration, storageKey, token]);

  return {
    isGenerating,
    phase,
    statusMessage,
    startedAtMs,
    milestones,
    error,
    setError,
    failureKind,
    startGeneration,
    retryGeneration,
    // Retry is offered by what went wrong, not by whether a job id happens to
    // exist: a build that never started is the most retryable case of all,
    // while a rejected intake can never succeed on an identical retry.
    canRetry: phase === "failed" && isRetryableGenerationFailure(failureKind) && !isGenerating,
    hasPendingGeneration: Boolean(getPendingGeneration(storageKey)),
  };
}
