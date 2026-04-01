"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getGenerationJob } from "@/lib/api";
import type { GenerationJobResponse, GenerationJobStatus } from "@/lib/types";

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

function savePendingGeneration(storageKey: string | null, pending: PendingGenerationState): void {
  if (!storageKey || typeof window === "undefined") {
    return;
  }
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
    return `Your plan request is queued and waiting for the runner.${suffix}`;
  }
  if (status === "running") {
    return `Your plan is processing in the background.${suffix}`;
  }
  return "Finalizing your plan.";
}

async function createJobWithReconnect(
  createJob: (clientRequestId: string) => Promise<GenerationJobResponse>,
  clientRequestId: string,
  setStatusMessage: (message: string | null) => void,
): Promise<GenerationJobResponse> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      return await createJob(clientRequestId);
    } catch (error) {
      lastError = error;
      if (attempt === 3) {
        break;
      }
      setStatusMessage("Connection dropped while starting the job. Reconnecting to the same request…");
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
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const recoveryAttemptedRef = useRef<string | null>(null);

  const startGeneration = useCallback(
    async (options: StartGenerationOptions = {}) => {
      if (!token || !storageKey || isGenerating) {
        return;
      }

      setError(null);
      setIsGenerating(true);
      const recovered = options.recovered ?? false;
      const clientRequestId = options.clientRequestId ?? buildClientRequestId();
      const pendingCreatedAt = new Date().toISOString();
      savePendingGeneration(storageKey, {
        clientRequestId,
        createdAt: pendingCreatedAt,
      });

      try {
        setStatusMessage(
          recovered
            ? "Reconnecting to your existing plan generation request."
            : "Submitting your plan generation request.",
        );
        const createdJob = await createJobWithReconnect(createJob, clientRequestId, setStatusMessage);
        const createdAtMs = Date.parse(createdJob.created_at || pendingCreatedAt) || Date.now();
        savePendingGeneration(storageKey, {
          clientRequestId,
          jobId: createdJob.job_id,
          createdAt: createdJob.created_at || pendingCreatedAt,
        });

        for (;;) {
          const currentJob = await getGenerationJob(token, createdJob.job_id);

          savePendingGeneration(storageKey, {
            clientRequestId,
            jobId: currentJob.job_id,
            createdAt: currentJob.created_at || pendingCreatedAt,
          });

          if (currentJob.status === "completed" || currentJob.status === "review_required") {
            const planId = currentJob.plan_id || currentJob.latest_plan_id;
            if (!planId) {
              clearPendingGeneration(storageKey);
              throw new Error("Generation finished, but no saved plan was returned.");
            }
            clearPendingGeneration(storageKey);
            setStatusMessage(null);
            setIsGenerating(false);
            onComplete({
              planId,
              status: currentJob.status,
              recovered,
            });
            return;
          }

          if (currentJob.status === "failed") {
            clearPendingGeneration(storageKey);
            throw new Error(currentJob.error || "Plan generation failed.");
          }

          setStatusMessage(statusMessageForJob(currentJob.status, createdAtMs));
          await sleep(getPollDelay(createdAtMs));
        }
      } catch (generationError) {
        setIsGenerating(false);
        setStatusMessage(null);
        setError(
          generationError instanceof Error ? generationError.message : "Unable to generate your plan.",
        );
      }
    },
    [createJob, isGenerating, onComplete, storageKey, token],
  );

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
    statusMessage,
    error,
    setError,
    startGeneration,
    hasPendingGeneration: Boolean(getPendingGeneration(storageKey)),
  };
}
