"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { retryGenerationJob } from "@/lib/api";
import { useAppSession } from "./auth-provider";
import { useGenerationStatus } from "./generation-status-provider";

function formatElapsed(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes === 0) {
    return `${seconds}s`;
  }
  return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
}

const CELEBRATION_DURATION_MS = 1_600;
const RIBBON_DISMISSED_KEY = "unlxck:generation-ribbon-dismissed";
const latestJobDismissKey = (jobId: string) => `${RIBBON_DISMISSED_KEY}:${jobId}`;
type PassiveLatestJobStatus = "failed" | "review_required" | "completed" | "queued" | "running";

export function shouldRenderPassiveLatestJobRibbon(
  latestJob:
    | { status?: PassiveLatestJobStatus | null; plan_id?: string | null; latest_plan_id?: string | null }
    | null
    | undefined,
): boolean {
  if (!latestJob) return false;
  if (latestJob.status === "failed") return true;
  if (latestJob.status === "review_required" && Boolean(latestJob.plan_id)) return true;
  if (latestJob.status === "completed" && !latestJob.plan_id) return true;
  return false;
}

export function latestFailedJobHasOpenablePlan(
  latestJob:
    | { status?: string | null; plan_id?: string | null; latest_plan_id?: string | null }
    | null
    | undefined,
): boolean {
  if (!latestJob || latestJob.status !== "failed") {
    return false;
  }
  return Boolean(latestJob.plan_id || latestJob.latest_plan_id);
}

export function getGenerationStatusTarget(
  phase: string | null,
  planId: string | null,
  terminalStatus: "completed" | "review_required" | null,
  source: string | null,
  athleteId: string | null,
): `/generate` | `/admin/athletes/${string}` | `/plans/${string}` | `/plans/${string}?review_required=1` | null {
  if (phase === "queued" || phase === "running" || phase === "finalizing") {
    if (source === "admin_latest_intake" && athleteId) {
      return `/admin/athletes/${athleteId}`;
    }
    if (source === "admin_triage_resume") {
      if (planId) return `/plans/${planId}`;
      if (athleteId) return `/admin/athletes/${athleteId}`;
    }
    return "/generate";
  }

  if (phase === "completed" && planId) {
    if (terminalStatus === "review_required") {
      return `/plans/${planId}?review_required=1`;
    }
    return `/plans/${planId}`;
  }
  return null;
}

export function GlobalGenerationStatus() {
  const { session } = useAppSession();
  const { isActive, statusMessage, phase, jobId, planId, terminalStatus, startedAtMs, refreshStatus, latestJob, source, athleteId } = useGenerationStatus();
  const [now, setNow] = useState(() => Date.now());
  const [isCelebrating, setIsCelebrating] = useState(false);
  const [isDismissed, setIsDismissed] = useState(false);
  const [isRetryingLatest, setIsRetryingLatest] = useState(false);
  const [retryLatestError, setRetryLatestError] = useState<string | null>(null);
  const previousPhaseRef = useRef(phase);
  const previousGenerationKeyRef = useRef<string | null>(null);

  const isFailed = phase === "failed";
  const isCompleted = phase === "completed";
  const navigationTarget = getGenerationStatusTarget(phase, planId, terminalStatus, source, athleteId);
  const ctaLabel = isCompleted && planId ? "View" : navigationTarget ? "Open" : "Refresh";
  const showElapsed = isActive && !isCompleted && !isFailed && startedAtMs !== null;

  useEffect(() => {
    if (!showElapsed) {
      return;
    }
    setNow(Date.now());
    const interval = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [showElapsed]);

  useEffect(() => {
    if (previousPhaseRef.current !== "completed" && phase === "completed") {
      setIsCelebrating(true);
      const reduceMotion = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (!reduceMotion && typeof navigator !== "undefined" && typeof navigator.vibrate === "function") {
        try {
          navigator.vibrate(20);
        } catch {
          // Vibration unavailable; silent celebration is fine.
        }
      }
      const timer = window.setTimeout(() => setIsCelebrating(false), CELEBRATION_DURATION_MS);
      previousPhaseRef.current = phase;
      return () => window.clearTimeout(timer);
    }
    previousPhaseRef.current = phase;
  }, [phase]);

  useEffect(() => {
    try {
      const latestDismissed = latestJob?.job_id ? window.localStorage.getItem(latestJobDismissKey(latestJob.job_id)) === "1" : false;
      setIsDismissed(latestDismissed || window.localStorage.getItem(RIBBON_DISMISSED_KEY) === "1");
    } catch {
      setIsDismissed(false);
    }
  }, [latestJob?.job_id]);

  useEffect(() => {
    if (!isActive) {
      previousGenerationKeyRef.current = null;
      return;
    }
    const generationKey = jobId && startedAtMs ? `${jobId}:${startedAtMs}` : null;
    if (!generationKey) {
      return;
    }
    if (previousGenerationKeyRef.current && previousGenerationKeyRef.current !== generationKey) {
      setIsDismissed(false);
      try {
        window.localStorage.removeItem(RIBBON_DISMISSED_KEY);
      } catch {}
    }
    previousGenerationKeyRef.current = generationKey;
  }, [isActive, jobId, startedAtMs]);

  if (!isActive && !latestJob) {
    return null;
  }

  const mapLatestError = (error?: string | null): string => {
    if (!error) return "Generation failed unexpectedly. Retry or contact support.";
    if (error.includes("Stage 2 first_pass prompt too large")) return "Your plan was too large to finalize automatically. Retry is available.";
    if (error.includes("Stage 1 planner timed out")) return "Generation took too long and stopped. Retry is available.";
    if (error.includes("Plan generation failed unexpectedly")) return "Generation failed unexpectedly. Retry or contact support.";
    return "Generation failed unexpectedly. Retry or contact support.";
  };

  const dismissCurrentBanner = () => {
    setIsDismissed(true);
    try {
      if (!isActive && latestJob?.job_id && (latestJob.status === "failed" || latestJob.status === "review_required")) {
        window.localStorage.setItem(latestJobDismissKey(latestJob.job_id), "1");
        return;
      }
      window.localStorage.setItem(RIBBON_DISMISSED_KEY, "1");
    } catch {}
  };

  if (!isActive && latestJob) {
    if (!shouldRenderPassiveLatestJobRibbon(latestJob)) {
      return null;
    }
    if (isDismissed && (latestJob.status === "failed" || latestJob.status === "review_required")) {
      return null;
    }
    if (latestJob.status === "failed") {
      const failedPlanId = latestJob.plan_id || latestJob.latest_plan_id || null;
      if (latestFailedJobHasOpenablePlan(latestJob) && failedPlanId) {
        return (
          <div className="global-generation-status global-generation-status-completed">
            <Link href={`/plans/${failedPlanId}`} className="global-generation-status-main">
              <div className="global-generation-status-message">Your plan is saved and ready.</div>
              <span className="global-generation-status-cta-label">Open plan</span>
            </Link>
            <button type="button" className="global-generation-status-dismiss" aria-label="Hide generation ribbon" onClick={dismissCurrentBanner}>×</button>
          </div>
        );
      }
      return (
        <div className="global-generation-status global-generation-status-failed">
          <div className="global-generation-status-main">
            <div className="global-generation-status-content">
              <span className="global-generation-status-text">
                <span className="global-generation-status-message">{mapLatestError(latestJob.error)}</span>
{latestJob.completed_at ? <span className="global-generation-status-elapsed" suppressHydrationWarning>Completed {new Date(latestJob.completed_at).toLocaleString()}</span> : null}
              </span>
              {latestJob.can_retry ? (
                <button
                  type="button"
                  className="global-generation-status-cta-label"
                  disabled={isRetryingLatest}
                  onClick={() => {
                    if (!session?.access_token || isRetryingLatest) return;
                    setRetryLatestError(null);
                    setIsRetryingLatest(true);
                    void retryGenerationJob(session.access_token, latestJob.job_id)
                      .then(() => refreshStatus())
                      .catch(() => setRetryLatestError("Retry failed. Open Generate and try again."))
                      .finally(() => setIsRetryingLatest(false));
                  }}
                >
                  {isRetryingLatest ? "Retrying..." : "Retry"}
                </button>
              ) : null}
            </div>
            {retryLatestError ? <div className="global-generation-status-message">{retryLatestError}</div> : null}
          </div>
          <button type="button" className="global-generation-status-dismiss" aria-label="Hide generation ribbon" onClick={dismissCurrentBanner}>×</button>
        </div>
      );
    }
    if (latestJob.status === "review_required" && latestJob.plan_id) {
      return (
        <div className="global-generation-status global-generation-status-completed">
          <Link href={`/plans/${latestJob.plan_id}?review_required=1`} className="global-generation-status-main">
            <div className="global-generation-status-message">Your plan is ready for review</div>
            <span className="global-generation-status-cta-label">Open plan</span>
          </Link>
          <button type="button" className="global-generation-status-dismiss" aria-label="Hide generation ribbon" onClick={dismissCurrentBanner}>×</button>
        </div>
      );
    }
    if (!latestJob.plan_id && latestJob.status === "completed") {
      return <div className="global-generation-status"><div className="global-generation-status-main">Your plan was generated but needs recovery/support</div></div>;
    }
  }

  const canNavigateToPlan = Boolean(navigationTarget);
  const elapsedLabel = showElapsed && startedAtMs !== null ? formatElapsed(now - startedAtMs) : null;
  const className = [
    "global-generation-status",
    isFailed ? "global-generation-status-failed" : "",
    isCompleted ? "global-generation-status-completed" : "",
    isCelebrating ? "global-generation-status-celebrating" : "",
  ].filter(Boolean).join(" ");

  if (!statusMessage && !phase && !navigationTarget) {
    return null;
  }

  if (isDismissed) {
    return (
      <button
        type="button"
        className="global-generation-status-reopen"
        aria-label="Show generation ribbon"
        onClick={() => {
          setIsDismissed(false);
          try {
            if (!isActive && latestJob?.job_id && (latestJob.status === "failed" || latestJob.status === "review_required")) {
              window.localStorage.removeItem(latestJobDismissKey(latestJob.job_id));
            } else {
              window.localStorage.removeItem(RIBBON_DISMISSED_KEY);
            }
          } catch {}
        }}
      >
        Show plan build
      </button>
    );
  }

  const content = (
    <>
      <div className="global-generation-status-content">
        <span className="global-generation-status-indicator" aria-hidden="true">
          {isCompleted ? (
            <span className="global-generation-status-check">&#10003;</span>
          ) : (
            <span className="global-generation-status-pulse" />
          )}
        </span>
        <span className="global-generation-status-text">
          <span className="global-generation-status-message">{statusMessage}</span>
          {elapsedLabel ? (
            <span className="global-generation-status-elapsed" aria-label={`Elapsed time ${elapsedLabel}`}>
              {elapsedLabel}
            </span>
          ) : null}
        </span>
        <span className="global-generation-status-cta">
          <span className="global-generation-status-cta-label">{ctaLabel}</span>
          <span className="global-generation-status-arrow" aria-hidden="true">→</span>
        </span>
      </div>
      {!isFailed && !isCompleted && (
        <div className="global-generation-status-rail" aria-hidden="true">
          <span className="global-generation-status-line" />
        </div>
      )}
      {isCelebrating ? <span className="global-generation-status-celebrate-glow" aria-hidden="true" /> : null}
    </>
  );

  return (
    <div className={className}>
      {canNavigateToPlan && navigationTarget ? (
        <Link
          href={navigationTarget}
          className="global-generation-status-main"
          aria-label={
            isCompleted
              ? "Plan ready. Tap to view."
              : "Generation in progress. Tap to open generation status."
          }
        >
          {content}
        </Link>
      ) : (
        <button
          type="button"
          className="global-generation-status-main"
          aria-label={isFailed ? "Plan failed. Tap to refresh status." : isCompleted ? "Plan completed. Tap to refresh status." : "Generation in progress. Tap to refresh status."}
          onClick={() => {
            refreshStatus();
          }}
        >
          {content}
        </button>
      )}
      <button
        type="button"
        className="global-generation-status-dismiss"
        aria-label="Hide generation ribbon"
        onClick={dismissCurrentBanner}
      >
        ×
      </button>
    </div>
  );
}
