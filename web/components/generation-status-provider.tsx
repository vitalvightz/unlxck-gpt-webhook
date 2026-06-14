"use client";

import { createContext, useContext, useEffect, useRef, useState, useCallback, type ReactNode } from "react";
import { getActiveGenerationJob, getGenerationJob, getLatestGenerationJob } from "@/lib/api";
import { isPreStartStaleGenerationJob, resolveTerminalJobPlanId } from "@/lib/generation-controller";
import { isExpiredPendingGeneration, isStaleVisibleGenerationJob, normalizeLegacyGenerationJobStatus } from "@/lib/generation-status-guards";
import type { GenerationJobResponse, GenerationJobStatus } from "@/lib/types";

export type GlobalGenerationPhase = "queued" | "running" | "finalizing" | "completed" | "failed" | null;
export type GlobalTerminalGenerationStatus = "completed" | "review_required" | null;

interface GenerationStatusContextValue {
  phase: GlobalGenerationPhase;
  jobId: string | null;
  clientRequestId: string | null;
  planId: string | null;
  athleteId: string | null;
  source: string | null;
  isActive: boolean;
  statusMessage: string | null;
  terminalStatus: GlobalTerminalGenerationStatus;
  startedAtMs: number | null;
  refreshStatus: () => void;
  latestJob: GenerationJobResponse | null;
}

const GenerationStatusContext = createContext<GenerationStatusContextValue | null>(null);
const PENDING_GENERATION_PREFIX = "unlxck:pending-generation:";
const GLOBAL_STATUS_POLL_MS = 15_000;
const INITIAL_STATUS_CHECK_DELAY_MS = 900;

interface PendingGenerationState {
  clientRequestId: string;
  jobId?: string | null;
  createdAt: string;
}

type StoredPendingGenerationState = PendingGenerationState & {
  storageKey: string;
  createdAtMs: number;
};

export function shouldUseLocalPendingForRecovery(pending: PendingGenerationState | null): boolean {
  return Boolean(pending?.jobId);
}

function parsePendingGeneration(storageKey: string): StoredPendingGenerationState | null {
  if (typeof window === "undefined") return null;

  const raw = window.localStorage.getItem(storageKey);
  if (!raw) return null;

  try {
    const decoded = JSON.parse(raw) as PendingGenerationState;
    if (!decoded?.clientRequestId) {
      window.localStorage.removeItem(storageKey);
      return null;
    }
    const createdAtMs = Date.parse(decoded.createdAt || "");
    return {
      ...decoded,
      storageKey,
      createdAtMs: Number.isFinite(createdAtMs) ? createdAtMs : 0,
    };
  } catch {
    window.localStorage.removeItem(storageKey);
    return null;
  }
}

function listPendingGenerations(): StoredPendingGenerationState[] {
  if (typeof window === "undefined") return [];

  return Object.keys(window.localStorage)
    .filter((key) => key.startsWith(PENDING_GENERATION_PREFIX))
    .map(parsePendingGeneration)
    .filter((pending): pending is StoredPendingGenerationState => pending !== null)
    .sort((a, b) => b.createdAtMs - a.createdAtMs);
}

function getPendingGeneration(): PendingGenerationState | null {
  const [latest, ...duplicates] = listPendingGenerations();

  duplicates.forEach((pending) => {
    window.localStorage.removeItem(pending.storageKey);
  });

  return latest ?? null;
}

function savePendingGeneration(pending: PendingGenerationState): void {
  if (typeof window === "undefined") return;
  const existing = listPendingGenerations();
  existing.forEach((item) => {
    window.localStorage.removeItem(item.storageKey);
  });
  const key = `${PENDING_GENERATION_PREFIX}self`;
  window.localStorage.setItem(key, JSON.stringify(pending));
}

function clearPendingGenerations(): void {
  if (typeof window === "undefined") return;

  Object.keys(window.localStorage)
    .filter((key) => key.startsWith(PENDING_GENERATION_PREFIX))
    .forEach((key) => window.localStorage.removeItem(key));
}

function isTerminalStatus(status: GenerationJobStatus): boolean {
  return status === "completed" || status === "review_required" || status === "failed";
}

export function shouldRetainLatestJob(job: GenerationJobResponse | null | undefined): boolean {
  if (!job) return false;
  const normalizedStatus = normalizeLegacyGenerationJobStatus(job.status) as GenerationJobStatus;
  // A terminal job with no openable plan (no plan_id and no latest_plan_id) has
  // nothing to show or act on, so it must not linger as a passive ribbon —
  // UNLESS it is a protected triage outcome that lives only on the job, in
  // which case the ribbon must keep surfacing the "admin review required"
  // state so the user can see it and an admin can act on it.
  if (isTerminalStatus(normalizedStatus) && !resolveTerminalJobPlanId(job)) {
    return job.requires_admin_resume === true;
  }
  return true;
}

function phaseFromStatus(status: GenerationJobStatus): GlobalGenerationPhase {
  if (status === "queued") return "queued";
  if (status === "running") return "running";
  if (status === "completed" || status === "review_required") return "completed";
  if (status === "failed") return "failed";
  return null;
}

function statusMessage(phase: GlobalGenerationPhase, terminalStatus: GlobalTerminalGenerationStatus): string {
  switch (phase) {
    case "queued":
      return "Plan request queued...";
    case "running":
      return "Generating plan...";
    case "finalizing":
      return "Finalizing plan...";
    case "completed":
      return terminalStatus === "review_required" ? "Plan ready for review." : "Plan ready!";
    case "failed":
      return "Plan failed. Try again.";
    default:
      return "";
  }
}

interface GenerationStatusProviderProps {
  children: ReactNode;
  token: string | null;
}

export function GenerationStatusProvider({ children, token }: GenerationStatusProviderProps) {
  const [phase, setPhase] = useState<GlobalGenerationPhase>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [clientRequestId, setClientRequestId] = useState<string | null>(null);
  const [planId, setPlanId] = useState<string | null>(null);
  const [athleteId, setAthleteId] = useState<string | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const [statusMessageText, setStatusMessageText] = useState<string | null>(null);
  const [terminalStatus, setTerminalStatus] = useState<GlobalTerminalGenerationStatus>(null);
  const [startedAtMs, setStartedAtMs] = useState<number | null>(null);
  const [latestJob, setLatestJob] = useState<GenerationJobResponse | null>(null);

  // Track the clear timeout so we can cancel it on unmount — prevents
  // state updates on an unmounted component
  const clearTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isCheckingRef = useRef(false);
  const wasAuthenticatedRef = useRef(Boolean(token));
  const latestTokenRef = useRef(token);
  const checkSequenceRef = useRef(0);

  const resetGenerationState = useCallback(() => {
    setPhase(null);
    setJobId(null);
    setClientRequestId(null);
    setPlanId(null);
    setAthleteId(null);
    setSource(null);
    setStatusMessageText(null);
    setTerminalStatus(null);
    setStartedAtMs(null);
    setLatestJob(null);
  }, []);

  useEffect(() => {
    latestTokenRef.current = token;
    checkSequenceRef.current++;
    isCheckingRef.current = false;
    if (clearTimerRef.current !== null) {
      clearTimeout(clearTimerRef.current);
      clearTimerRef.current = null;
    }
    resetGenerationState();
    // Clear local pending state on every auth change so the previous session's
    // global key cannot leak into the next authenticated user; backend
    // active/latest endpoints restore the current user's real state after login.
    clearPendingGenerations();
  }, [token, resetGenerationState]);

  // Cancel any pending clear timer when the component unmounts
  useEffect(() => {
    return () => {
      if (clearTimerRef.current !== null) {
        clearTimeout(clearTimerRef.current);
      }
    };
  }, []);

  const checkStatus = useCallback(async () => {
    if (token && isCheckingRef.current) return;
    const sequence = ++checkSequenceRef.current;

    if (!token) {
      checkSequenceRef.current++;
      if (wasAuthenticatedRef.current) {
        clearPendingGenerations();
      }
      resetGenerationState();
      wasAuthenticatedRef.current = false;
      isCheckingRef.current = false;
      return;
    }

    wasAuthenticatedRef.current = true;

    if (isCheckingRef.current) {
      return;
    }

    isCheckingRef.current = true;

    try {
      let activePending: PendingGenerationState | null = null;
      try {
        const activeJob = await getActiveGenerationJob(token);
        if (sequence !== checkSequenceRef.current || !latestTokenRef.current) {
          return;
        }
        if (activeJob?.client_request_id && activeJob.created_at) {
          activePending = {
            clientRequestId: activeJob.client_request_id,
            jobId: activeJob.job_id,
            createdAt: activeJob.created_at,
          };
          setLatestJob(null);
          savePendingGeneration(activePending);
        }
      } catch {
        // Active endpoint unavailable: fall back to local pending recovery.
      }
      if (!activePending) {
        const pending = getPendingGeneration();
        if (pending && isExpiredPendingGeneration(pending.createdAt)) {
          clearPendingGenerations();
        } else if (shouldUseLocalPendingForRecovery(pending)) {
          activePending = pending;
        } else {
          clearPendingGenerations();
        }
      }
      if (!activePending) {
        try {
          const latest = await getLatestGenerationJob(token);
          if (sequence !== checkSequenceRef.current || !latestTokenRef.current) return;
          setLatestJob(shouldRetainLatestJob(latest) ? latest : null);
        } catch {
          setLatestJob(null);
        }
        setPhase(null);
        setJobId(null);
        setClientRequestId(null);
        setPlanId(null);
        setAthleteId(null);
        setSource(null);
        setStatusMessageText(null);
        setTerminalStatus(null);
        setStartedAtMs(null);
        return;
      }

      setClientRequestId(activePending.clientRequestId);
      const pendingCreatedAt = Date.parse(activePending.createdAt || "");
      setStartedAtMs(Number.isFinite(pendingCreatedAt) ? pendingCreatedAt : null);
      setLatestJob(null);

      if (activePending.jobId && token) {
        try {
          const job: GenerationJobResponse = await getGenerationJob(token, activePending.jobId);
          if (sequence !== checkSequenceRef.current || !latestTokenRef.current) {
            return;
          }
          const stalledBeforeStart = isPreStartStaleGenerationJob(job);
          const staleVisibleJob = isStaleVisibleGenerationJob(job);
          const normalizedStatus = normalizeLegacyGenerationJobStatus(job.status) as GenerationJobStatus;
          const newPhase = stalledBeforeStart || staleVisibleJob ? "failed" : phaseFromStatus(normalizedStatus);
          const newTerminalStatus = normalizedStatus === "completed" || normalizedStatus === "review_required" ? normalizedStatus : null;
          setPhase(newPhase);
          setJobId(activePending.jobId);
          setTerminalStatus(newTerminalStatus);
          setStatusMessageText(stalledBeforeStart || staleVisibleJob ? "Build stalled — retry" : statusMessage(newPhase, newTerminalStatus));

          if (normalizedStatus === "completed" || normalizedStatus === "review_required") {
            setPlanId(job.plan_id || null);
          } else {
            setPlanId(null);
          }
          setAthleteId(job.athlete_id || null);
          setSource(job.source || null);

          if (stalledBeforeStart || staleVisibleJob || isTerminalStatus(normalizedStatus)) {
            clearPendingGenerations();

            // Schedule the status clear — cancel any previous pending clear first
            if (clearTimerRef.current !== null) {
              clearTimeout(clearTimerRef.current);
            }
            const delay = stalledBeforeStart || staleVisibleJob || normalizedStatus === "failed" ? 3000 : 5000;
            clearTimerRef.current = setTimeout(() => {
              clearTimerRef.current = null;
              setPhase(null);
              setJobId(null);
              setClientRequestId(null);
              setPlanId(null);
              setAthleteId(null);
              setSource(null);
              setStatusMessageText(null);
              setTerminalStatus(null);
              setStartedAtMs(null);
            }, delay);
          }
        } catch {
          clearPendingGenerations();
          setPhase(null);
          setJobId(null);
          setClientRequestId(null);
          setPlanId(null);
          setAthleteId(null);
          setSource(null);
          setStatusMessageText(null);
          setTerminalStatus(null);
          setStartedAtMs(null);
          setLatestJob(null);
        }
      } else {
        clearPendingGenerations();
        setPhase(null);
        setJobId(null);
        setClientRequestId(null);
        setPlanId(null);
        setAthleteId(null);
        setSource(null);
        setStatusMessageText(null);
        setTerminalStatus(null);
        setStartedAtMs(null);
      }
    } finally {
      isCheckingRef.current = false;
    }
  }, [token, resetGenerationState]);

  useEffect(() => {
    const initialCheckTimer = window.setTimeout(() => {
      void checkStatus();
    }, token ? INITIAL_STATUS_CHECK_DELAY_MS : 0);

    const interval = setInterval(() => {
      if (getPendingGeneration()) {
        void checkStatus();
      }
    }, GLOBAL_STATUS_POLL_MS);

    const handleStorageChange = () => {
      void checkStatus();
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void checkStatus();
      }
    };

    window.addEventListener("storage", handleStorageChange);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      window.clearTimeout(initialCheckTimer);
      clearInterval(interval);
      window.removeEventListener("storage", handleStorageChange);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [checkStatus]);

  const value: GenerationStatusContextValue = {
    phase,
    jobId,
    clientRequestId,
    planId,
    athleteId,
    source,
    isActive: phase !== null,
    statusMessage: statusMessageText,
    terminalStatus,
    startedAtMs,
    refreshStatus: checkStatus,
    latestJob,
  };

  return (
    <GenerationStatusContext.Provider value={value}>
      {children}
    </GenerationStatusContext.Provider>
  );
}

export function useGenerationStatus(): GenerationStatusContextValue {
  const context = useContext(GenerationStatusContext);
  if (!context) {
    throw new Error("useGenerationStatus must be used within GenerationStatusProvider");
  }
  return context;
}
