"use client";

import { createContext, useContext, useEffect, useRef, useState, useCallback, type ReactNode } from "react";
import { getGenerationJob } from "@/lib/api";
import type { GenerationJobResponse, GenerationJobStatus } from "@/lib/types";

export type GlobalGenerationPhase = "queued" | "running" | "finalizing" | "completed" | "failed" | null;

interface GenerationStatusContextValue {
  phase: GlobalGenerationPhase;
  jobId: string | null;
  clientRequestId: string | null;
  planId: string | null;
  isActive: boolean;
  statusMessage: string | null;
  refreshStatus: () => void;
}

const GenerationStatusContext = createContext<GenerationStatusContextValue | null>(null);
const PENDING_GENERATION_PREFIX = "unlxck:pending-generation:";
const GLOBAL_STATUS_POLL_MS = 15_000;

interface PendingGenerationState {
  clientRequestId: string;
  jobId?: string | null;
  createdAt: string;
}

type StoredPendingGenerationState = PendingGenerationState & {
  storageKey: string;
  createdAtMs: number;
};

function parsePendingGeneration(storageKey: string): StoredPendingGenerationState | null {
  if (typeof window === "undefined") return null;

  const raw = window.sessionStorage.getItem(storageKey);
  if (!raw) return null;

  try {
    const decoded = JSON.parse(raw) as PendingGenerationState;
    if (!decoded?.clientRequestId) {
      window.sessionStorage.removeItem(storageKey);
      return null;
    }
    const createdAtMs = Date.parse(decoded.createdAt || "");
    return {
      ...decoded,
      storageKey,
      createdAtMs: Number.isFinite(createdAtMs) ? createdAtMs : 0,
    };
  } catch {
    window.sessionStorage.removeItem(storageKey);
    return null;
  }
}

function listPendingGenerations(): StoredPendingGenerationState[] {
  if (typeof window === "undefined") return [];

  return Object.keys(window.sessionStorage)
    .filter((key) => key.startsWith(PENDING_GENERATION_PREFIX))
    .map(parsePendingGeneration)
    .filter((pending): pending is StoredPendingGenerationState => pending !== null)
    .sort((a, b) => b.createdAtMs - a.createdAtMs);
}

function getPendingGeneration(): PendingGenerationState | null {
  const [latest, ...duplicates] = listPendingGenerations();

  duplicates.forEach((pending) => {
    window.sessionStorage.removeItem(pending.storageKey);
  });

  return latest ?? null;
}

function clearPendingGenerations(): void {
  if (typeof window === "undefined") return;

  Object.keys(window.sessionStorage)
    .filter((key) => key.startsWith(PENDING_GENERATION_PREFIX))
    .forEach((key) => window.sessionStorage.removeItem(key));
}

function isTerminalStatus(status: GenerationJobStatus): boolean {
  return status === "completed" || status === "review_required" || status === "failed";
}

function phaseFromStatus(status: GenerationJobStatus): GlobalGenerationPhase {
  if (status === "queued") return "queued";
  if (status === "running") return "running";
  if (status === "completed" || status === "review_required") return "completed";
  if (status === "failed") return "failed";
  return null;
}

function statusMessage(phase: GlobalGenerationPhase): string {
  switch (phase) {
    case "queued":
      return "Plan request queued...";
    case "running":
      return "Generating plan...";
    case "finalizing":
      return "Finalizing plan...";
    case "completed":
      return "Plan ready!";
    case "failed":
      return "Generation failed";
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
  const [statusMessageText, setStatusMessageText] = useState<string | null>(null);

  // Track the clear timeout so we can cancel it on unmount — prevents
  // state updates on an unmounted component
  const clearTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isCheckingRef = useRef(false);

  // Cancel any pending clear timer when the component unmounts
  useEffect(() => {
    return () => {
      if (clearTimerRef.current !== null) {
        clearTimeout(clearTimerRef.current);
      }
    };
  }, []);

  const checkStatus = useCallback(async () => {
    if (isCheckingRef.current) {
      return;
    }

    isCheckingRef.current = true;

    try {
      const pending = getPendingGeneration();

      if (!pending) {
        setPhase(null);
        setJobId(null);
        setClientRequestId(null);
        setPlanId(null);
        setStatusMessageText(null);
        return;
      }

      setClientRequestId(pending.clientRequestId);

      if (pending.jobId && token) {
        try {
          const job: GenerationJobResponse = await getGenerationJob(token, pending.jobId);
          const newPhase = phaseFromStatus(job.status);
          setPhase(newPhase);
          setJobId(pending.jobId);
          setStatusMessageText(statusMessage(newPhase));

          if (job.status === "completed" || job.status === "review_required") {
            setPlanId(job.plan_id || job.latest_plan_id || null);
          }

          if (isTerminalStatus(job.status)) {
            clearPendingGenerations();

            // Schedule the status clear — cancel any previous pending clear first
            if (clearTimerRef.current !== null) {
              clearTimeout(clearTimerRef.current);
            }
            const delay = job.status === "failed" ? 3000 : 5000;
            clearTimerRef.current = setTimeout(() => {
              clearTimerRef.current = null;
              setPhase(null);
              setJobId(null);
              setClientRequestId(null);
              setPlanId(null);
              setStatusMessageText(null);
            }, delay);
          }
        } catch {
          // If we can't check status but have pending data, assume still running
          setPhase("running");
          setStatusMessageText("Generating plan...");
        }
      } else {
        setPhase("queued");
        setStatusMessageText("Plan request queued...");
      }
    } finally {
      isCheckingRef.current = false;
    }
  }, [token]);

  useEffect(() => {
    void checkStatus();

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
    isActive: phase !== null,
    statusMessage: statusMessageText,
    refreshStatus: checkStatus,
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
