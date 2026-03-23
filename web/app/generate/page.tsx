"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { createGenerationJob, getGenerationJob, getLatestPlan, ApiError } from "@/lib/api";
import { hydratePlanRequest } from "@/lib/onboarding";
import { PremiumLoadingScreen } from "@/components/premium-loading-screen";

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 5 * 60 * 1000;
const ACTIVE_GENERATION_STORAGE_KEY = "unlxck-active-generation-job";

type StoredGenerationJob = {
  athleteId: string;
  jobId: string;
  startedAtMs: number;
};

function readStoredGenerationJob(athleteId: string): StoredGenerationJob | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const raw = window.sessionStorage.getItem(ACTIVE_GENERATION_STORAGE_KEY);
    if (!raw) {
      return null;
    }

    const parsed = JSON.parse(raw) as Partial<StoredGenerationJob>;
    if (
      parsed.athleteId !== athleteId ||
      typeof parsed.jobId !== "string" ||
      !parsed.jobId ||
      typeof parsed.startedAtMs !== "number"
    ) {
      window.sessionStorage.removeItem(ACTIVE_GENERATION_STORAGE_KEY);
      return null;
    }

    if (Date.now() - parsed.startedAtMs >= POLL_TIMEOUT_MS) {
      window.sessionStorage.removeItem(ACTIVE_GENERATION_STORAGE_KEY);
      return null;
    }

    return {
      athleteId: parsed.athleteId,
      jobId: parsed.jobId,
      startedAtMs: parsed.startedAtMs,
    };
  } catch {
    window.sessionStorage.removeItem(ACTIVE_GENERATION_STORAGE_KEY);
    return null;
  }
}

function writeStoredGenerationJob(job: StoredGenerationJob) {
  if (typeof window === "undefined") {
    return;
  }

  window.sessionStorage.setItem(ACTIVE_GENERATION_STORAGE_KEY, JSON.stringify(job));
}

function clearStoredGenerationJob() {
  if (typeof window === "undefined") {
    return;
  }

  window.sessionStorage.removeItem(ACTIVE_GENERATION_STORAGE_KEY);
}

function buildPlanUrl(planId: string, reviewRequired: boolean): string {
  const search = new URLSearchParams();
  if (reviewRequired) {
    search.set("review_required", "1");
  }
  return `/plans/${encodeURIComponent(planId)}${search.toString() ? `?${search.toString()}` : ""}`;
}

export default function GeneratePage() {
  const router = useRouter();
  const { me, refreshMe, session } = useAppSession();
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const inFlightRef = useRef(false);
  const refreshMeRef = useRef(refreshMe);

  useEffect(() => {
    refreshMeRef.current = refreshMe;
  }, [refreshMe]);

  useEffect(() => {
    console.info("[generate-page] effect:entered", {
      hasSessionToken: Boolean(session?.access_token),
      hasMe: Boolean(me),
      inFlight: inFlightRef.current,
    });

    if (!session?.access_token || !me || inFlightRef.current) {
      return;
    }

    const payload = hydratePlanRequest(me);

    if (!payload.fight_date || !payload.athlete.technical_style.length) {
      console.warn("[generate-page] redirect:onboarding_incomplete_payload");
      router.replace("/onboarding");
      return;
    }

    const athleteId = me.profile.athlete_id;
    const token = session.access_token;
    let cancelled = false;
    inFlightRef.current = true;
    setError(null);

    const openSavedPlan = (planId: string, reviewRequired: boolean, message: string) => {
      clearStoredGenerationJob();
      setStatusMessage(message);
      void refreshMeRef.current().catch((refreshError) => {
        console.warn("[generate-page] refreshMe:failed_after_generation", refreshError);
      });
      router.replace(buildPlanUrl(planId, reviewRequired));
    };

    void (async () => {
      let didRecoverMissingJob = false;

      const recoverMissingJob = async (missingJobId: string, startedAtMs: number): Promise<string | null> => {
        console.warn("[generate-page] generation-job:missing", {
          athleteId,
          jobId: missingJobId,
          didRecoverMissingJob,
        });
        clearStoredGenerationJob();

        try {
          const latestPlan = await getLatestPlan(token);
          const latestPlanCreatedAtMs = Date.parse(latestPlan.created_at);
          if (
            Number.isFinite(latestPlanCreatedAtMs) &&
            latestPlanCreatedAtMs >= startedAtMs - POLL_INTERVAL_MS
          ) {
            openSavedPlan(
              latestPlan.plan_id,
              latestPlan.status === "review_required",
              "Your plan finished after the live tracker reset. Opening the saved plan now.",
            );
            return null;
          }
        } catch (planError) {
          if (!(planError instanceof ApiError && planError.status === 404)) {
            throw planError;
          }
        }

        if (didRecoverMissingJob) {
          throw new Error("Generation tracking was interrupted. Please refresh and try again.");
        }

        setStatusMessage("The job tracker reset while your plan was generating. Reconnecting now.");
        const replacementJob = await createGenerationJob(token, payload);
        console.info("[generate-page] generation-job:recovered", {
          missingJobId,
          replacementJob,
        });
        didRecoverMissingJob = true;
        writeStoredGenerationJob({
          athleteId,
          jobId: replacementJob.job_id,
          startedAtMs,
        });
        return replacementJob.job_id;
      };

      try {
        const existingJob = readStoredGenerationJob(athleteId);
        let jobId: string;
        let startedAtMs: number;

        if (existingJob) {
          console.info("[generate-page] generation-job:resumed", existingJob);
          jobId = existingJob.jobId;
          startedAtMs = existingJob.startedAtMs;
          setStatusMessage("Resuming your background generation job.");
        } else {
          setStatusMessage("Submitting your generation request and creating a background job.");
          const job = await createGenerationJob(token, payload);
          if (cancelled) {
            return;
          }
          console.info("[generate-page] generation-job:created", job);
          jobId = job.job_id;
          startedAtMs = Date.now();
          writeStoredGenerationJob({
            athleteId,
            jobId,
            startedAtMs,
          });
          setStatusMessage("Your job is queued. We'll keep checking until the saved plan is ready.");
        }

        while (!cancelled && Date.now() - startedAtMs < POLL_TIMEOUT_MS) {
          let currentJob;
          try {
            currentJob = await getGenerationJob(token, jobId);
          } catch (jobError) {
            if (jobError instanceof ApiError && jobError.status === 404) {
              const replacementJobId = await recoverMissingJob(jobId, startedAtMs);
              if (!replacementJobId || cancelled) {
                return;
              }
              jobId = replacementJobId;
              continue;
            }
            throw jobError;
          }

          if (cancelled) {
            return;
          }

          console.info("[generate-page] generation-job:polled", currentJob);
          writeStoredGenerationJob({
            athleteId,
            jobId: currentJob.job_id,
            startedAtMs,
          });

          if (currentJob.status === "queued") {
            setStatusMessage("Your plan request is queued. Stage 1 and Stage 2 will start shortly.");
          } else if (currentJob.status === "running") {
            setStatusMessage("Stage 1 generation and Stage 2 finalization are running in the background.");
          } else if (currentJob.status === "failed") {
            throw new Error(currentJob.error || "Plan generation failed.");
          } else if (
            currentJob.status === "completed" ||
            currentJob.status === "review_required"
          ) {
            const planId = currentJob.plan_id || currentJob.latest_plan_id;
            if (!planId) {
              throw new Error("Generation finished, but no saved plan was returned.");
            }

            openSavedPlan(
              planId,
              currentJob.status === "review_required",
              "Your plan is ready. Opening the saved plan now.",
            );
            return;
          }

          await new Promise((resolve) => window.setTimeout(resolve, POLL_INTERVAL_MS));
        }

        clearStoredGenerationJob();
        throw new Error("Plan generation is taking longer than expected. Please check back in a moment.");
      } catch (generationError) {
        console.error("[generate-page] generation:failed", generationError);
        clearStoredGenerationJob();
        if (generationError instanceof ApiError) {
          setError(generationError.message);
        } else if (generationError instanceof Error) {
          setError(generationError.message);
        } else {
          setError("Unable to generate your plan.");
        }
        setStatusMessage(null);
      } finally {
        inFlightRef.current = false;
      }
    })();

    return () => {
      cancelled = true;
      inFlightRef.current = false;
    };
  }, [me, router, session?.access_token]);

  return (
    <RequireAuth>
      <PremiumLoadingScreen error={error} statusMessage={statusMessage} />
    </RequireAuth>
  );
}
