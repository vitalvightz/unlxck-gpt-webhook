"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getGenerationJob, isRetryableApiFailure, retryGenerationJob } from "@/lib/api";
import type { GenerationJobResponse, GenerationJobStatus, ProgressMilestone } from "@/lib/types";

export type GenerationUiPhase =
  | "submitting"
  | "queued"
  | "running"
  | "reconnecting"
  | "finalizing"
  | "failed";

type PendingGenerationState = {
  clientRequestId: string;
  jobId?: string | null;
  createdAt: string;
};

type GenerationCompletion = {
  planId: string;
  status: Extract<GenerationJobStatus, "completed" | "review_required">;
  recovered: boolean;
};

type GenerationControllerOptions = {
  token: string | null;
  storageKey: string | null;
  createJob: (clientRequestId: string) => Promise<GenerationJobResponse>;
  onComplete: (result: GenerationCompletion) => void;
};

type StartGenerationOptions = {
  clientRequestId?: string;
  recovered?: boolean;
};

const INITIAL_POLL_MS = 2_000;
const MEDIUM_POLL_MS = 5_000;
const LONG_POLL_MS = 15_000;
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
  const raw = window.sessionStorage.getItem(storageKey);
  if (!raw) {
    return null;
  }
  try {
    const decoded = JSON.parse(raw) as PendingGenerationState;
    return decoded?.clientRequestId ? decoded : null;
  } catch {
    window.sessionStorage.removeItem(storageKey);
    return null;
  }
}

function clearOtherPendingGenerations(activeStorageKey: string | null): void {
  if (typeof window === "undefined") {
    return;
  }

  Object.keys(window.sessionStorage)
    .filter((key) => key.startsWith(PENDING_GENERATION_PREFIX) && key !== activeStorageKey)
    .forEach((key) => window.sessionStorage.removeItem(key));
}

function clearAllPendingGenerations(): void {
  if (typeof window === "undefined") {
    return;
  }

  Object.keys(window.sessionStorage)
    .filter((key) => key.startsWith(PENDING_GENERATION_PREFIX))
    .forEach((key) => window.sessionStorage.removeItem(key));
}

function savePendingGeneration(storageKey: string | null, pending: PendingGenerationState): void {
  if (!storageKey || typeof window === "undefined") {
    return;
  }
  clearOtherPendingGenerations(storageKey);
  window.sessionStorage.setItem(storageKey, JSON.stringify(pending));
}

function clearPendingGeneration(storageKey: string | null): void {
  if (!storageKey || typeof window === "undefined") {
    return;
  }
  window.sessionStorage.removeItem(storageKey);
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

function phaseForJobStatus(status: GenerationJobStatus): Exclude<GenerationUiPhase, "submitting" | "reconnecting" | "failed"> {
  if (status === "queued") {
    return "queued";
  }
  if (status === "running") {
    return "running";
  }
  return "finalizing";
}

async function createJobWithReconnect(
  createJob: (clientRequestId: string) => Promise<GenerationJobResponse>,
  clientRequestId: string,
  setStatusMessage: (message: string | null) => void,
  setPhase: (phase: GenerationUiPhase) => void,
): Promise<GenerationJobResponse> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      return await createJob(clientRequestId);
    } catch (error) {
      lastError = error;
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
}: GenerationControllerOptions) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [phase, setPhase] = useState<GenerationUiPhase>(() =>
    getPendingGeneration(storageKey) ? "reconnecting" : "submitting",
  );
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [milestones, setMilestones] = useState<ProgressMilestone[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [failedJobId, setFailedJobId] = useState<string | null>(null);
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

        savePendingGeneration(activeStorageKey, {
          clientRequestId,
          jobId: currentJob.job_id,
          createdAt: currentJob.created_at || pendingCreatedAtFallback,
        });

        if (currentJob.status === "completed" || currentJob.status === "review_required") {
          const planId = currentJob.plan_id || currentJob.latest_plan_id;
          if (!planId) {
            clearAllPendingGenerations();
            throw new Error("Generation finished, but no saved plan was returned.");
          }
          clearAllPendingGenerations();
          setPhase("finalizing");
          setStatusMessage("Final checks passed. Opening your saved plan.");
          setIsGenerating(false);
          await sleep(220);
          onComplete({
            planId,
            status: currentJob.status,
            recovered,
          });
          return;
        }

        if (currentJob.status === "failed") {
          clearAllPendingGenerations();
          setFailedJobId(currentJob.job_id);
          throw new Error(currentJob.error || "Plan generation failed.");
        }

        setPhase(phaseForJobStatus(currentJob.status));
        setStatusMessage(statusMessageForJob(currentJob.status, createdAtMs));
        await sleep(getPollDelay(createdAtMs));
      }
    },
    [onComplete],
  );

  const startGeneration = useCallback(
    async (options: StartGenerationOptions = {}) => {
      if (!token || !storageKey || isGenerating) {
        return;
      }

      setError(null);
      setFailedJobId(null);
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
        const createdJob = await createJobWithReconnect(createJob, clientRequestId, setStatusMessage, setPhase);
        const createdAtMs = Date.parse(createdJob.created_at || pendingCreatedAt) || Date.now();
        setStartedAtMs(createdAtMs);
        await watchJobUntilTerminal(
          token,
          storageKey,
          createdJob,
          clientRequestId,
          pendingCreatedAt,
          createdAtMs,
          recovered,
        );
      } catch (generationError) {
        clearPendingGeneration(storageKey);
        setIsGenerating(false);
        setStatusMessage(null);
        setPhase("failed");
        setError(mapGenerationErrorMessage(generationError));
      }
    },
    [createJob, isGenerating, storageKey, token, watchJobUntilTerminal],
  );

  const retryGeneration = useCallback(async () => {
    if (!token || !storageKey || isGenerating || !failedJobId) {
      return;
    }

    setError(null);
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
      setFailedJobId(null);
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
      setIsGenerating(false);
      setStatusMessage(null);
      setPhase("failed");
      setError(mapGenerationErrorMessage(retryError));
    }
  }, [failedJobId, isGenerating, storageKey, token, watchJobUntilTerminal]);

  useEffect(() => {
    if (!token || !storageKey || isGenerating) {
      return;
    }
    const pending = getPendingGeneration(storageKey);
    if (!pending) {
      return;
    }
    if (recoveryAttemptedRef.current === pending.clientRequestId) {
      return;
    }
    recoveryAttemptedRef.current = pending.clientRequestId;
    void startGeneration({
      clientRequestId: pending.clientRequestId,
      recovered: true,
    });
  }, [isGenerating, startGeneration, storageKey, token]);

  return {
    isGenerating,
    phase,
    statusMessage,
    startedAtMs,
    milestones,
    error,
    setError,
    startGeneration,
    retryGeneration,
    canRetry: Boolean(failedJobId) && !isGenerating,
    hasPendingGeneration: Boolean(getPendingGeneration(storageKey)),
  };
}
