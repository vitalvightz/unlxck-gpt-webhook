"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

import { cancelGenerationJob, retryGenerationJob } from "@/lib/api";
import { humanizeGenerationError } from "@/lib/generation-failure";
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

export function isProtectedTriageLatestJob(
  latestJob:
    | { stage2_status?: string | null; requires_admin_resume?: boolean | null }
    | null
    | undefined,
): boolean {
  if (!latestJob) {
    return false;
  }
  if (latestJob.requires_admin_resume === true) {
    return true;
  }
  const stage2 = String(latestJob.stage2_status || "").trim().toLowerCase();
  return stage2 === "triage_blocked";
}

export function shouldRenderPassiveLatestJobRibbon(
  latestJob:
    | {
        status?: PassiveLatestJobStatus | null;
        plan_id?: string | null;
        latest_plan_id?: string | null;
        stage2_status?: string | null;
        requires_admin_resume?: boolean | null;
      }
    | null
    | undefined,
): boolean {
  if (!latestJob) {
    return false;
  }

  if (latestJob.status === "failed") {
    return true;
  }

  if (latestJob.status === "review_required" && Boolean(latestJob.plan_id)) {
    return true;
  }

  // Triage outcomes have no plan_id and the backend reports them as
  // review_required. Surface them via the protected-triage ribbon copy.
  if (latestJob.status === "review_required" && isProtectedTriageLatestJob(latestJob)) {
    return true;
  }

  if (latestJob.status === "completed" && !latestJob.plan_id) {
    return true;
  }

  if (latestJob.status === "completed" && isProtectedTriageLatestJob(latestJob)) {
    return true;
  }

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

export function latestCompletedJobOpenablePlanId(
  latestJob:
    | { status?: string | null; plan_id?: string | null; latest_plan_id?: string | null }
    | null
    | undefined,
): string | null {
  if (!latestJob || latestJob.status !== "completed" || latestJob.plan_id) {
    return null;
  }

  return latestJob.latest_plan_id || null;
}

export function getPassiveLatestJobPlanTarget(
  latestJob:
    | { status?: string | null; plan_id?: string | null; latest_plan_id?: string | null }
    | null
    | undefined,
): `/plans/${string}` | null {
  if (!latestJob) {
    return null;
  }

  if (latestJob.status === "failed") {
    const planId = latestJob.plan_id || latestJob.latest_plan_id;
    return planId ? `/plans/${planId}` : null;
  }

  if (latestJob.status === "review_required" && latestJob.plan_id) {
    return `/plans/${latestJob.plan_id}`;
  }

  const completedPlanId = latestCompletedJobOpenablePlanId(latestJob);
  return completedPlanId ? `/plans/${completedPlanId}` : null;
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
      if (planId) {
        return `/plans/${planId}`;
      }

      if (athleteId) {
        return `/admin/athletes/${athleteId}`;
      }
    }

    return "/generate";
  }

  if (phase === "completed" && planId) {
    if (terminalStatus === "review_required") {
      return `/plans/${planId}?review_required=1`;
    }

    return `/plans/${planId}`;
  }

  // A failed build has no live workspace to open: /generate would mount the
  // build screen ("Saving your intake...") and then bounce back, which reads as
  // if generation restarted. The failed ribbon renders its own explicit
  // actions instead of a navigation target.
  return null;
}

export function isGenerationRibbonTargetRedundant(pathname: string | null, target: string | null): boolean {
  if (!pathname || !target) {
    return false;
  }

  const targetPath = target.split("?", 1)[0];
  return pathname === targetPath || (pathname === "/plans" && targetPath.startsWith("/plans/"));
}

export function GlobalGenerationStatus() {
  const { session } = useAppSession();
  const pathname = usePathname();
  const {
    isActive,
    isStalled,
    statusMessage,
    phase,
    jobId,
    planId,
    terminalStatus,
    startedAtMs,
    refreshStatus,
    latestJob,
    source,
    athleteId,
  } = useGenerationStatus();

  const [now, setNow] = useState(() => Date.now());
  const [isCelebrating, setIsCelebrating] = useState(false);
  const [isDismissed, setIsDismissed] = useState(false);
  const [resolvedDismissKey, setResolvedDismissKey] = useState<string | null>(null);
  const [isRetryingLatest, setIsRetryingLatest] = useState(false);
  const [retryLatestError, setRetryLatestError] = useState<string | null>(null);
  const [reopenPos, setReopenPos] = useState<{ x: number; y: number } | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  const previousPhaseRef = useRef(phase);
  const previousGenerationKeyRef = useRef<string | null>(null);
  const reopenRef = useRef<HTMLButtonElement>(null);
  const reopenDragRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    originX: number;
    originY: number;
    moved: boolean;
  } | null>(null);
  const reopenJustDraggedRef = useRef(false);

  // Keep the draggable "Show plan build" pill on-screen if the viewport resizes.
  useEffect(() => {
    if (!reopenPos) {
      return;
    }

    const clamp = () => {
      const el = reopenRef.current;
      const width = el?.offsetWidth ?? 0;
      const height = el?.offsetHeight ?? 0;
      const maxX = Math.max(8, window.innerWidth - width - 8);
      const maxY = Math.max(8, window.innerHeight - height - 8);

      setReopenPos((prev) =>
        prev
          ? {
              x: Math.min(Math.max(8, prev.x), maxX),
              y: Math.min(Math.max(8, prev.y), maxY),
            }
          : prev,
      );
    };

    window.addEventListener("resize", clamp);
    return () => window.removeEventListener("resize", clamp);
  }, [reopenPos]);

  const handleReopenPointerDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const el = reopenRef.current;
    if (!el) {
      return;
    }

    const rect = el.getBoundingClientRect();
    reopenDragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: rect.left,
      originY: rect.top,
      moved: false,
    };

    try {
      el.setPointerCapture(event.pointerId);
    } catch {
      // Pointer capture unsupported; dragging still works via window coords.
    }
  };

  const handleReopenPointerMove = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const drag = reopenDragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) {
      return;
    }

    const dx = event.clientX - drag.startX;
    const dy = event.clientY - drag.startY;

    // Ignore micro-movements so a tap still registers as a click.
    if (!drag.moved && Math.hypot(dx, dy) < 6) {
      return;
    }

    drag.moved = true;

    const el = reopenRef.current;
    const width = el?.offsetWidth ?? 0;
    const height = el?.offsetHeight ?? 0;
    const maxX = Math.max(8, window.innerWidth - width - 8);
    const maxY = Math.max(8, window.innerHeight - height - 8);

    setReopenPos({
      x: Math.min(Math.max(8, drag.originX + dx), maxX),
      y: Math.min(Math.max(8, drag.originY + dy), maxY),
    });
  };

  const handleReopenPointerUp = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const drag = reopenDragRef.current;
    if (!drag) {
      return;
    }

    reopenJustDraggedRef.current = drag.moved;
    reopenDragRef.current = null;

    try {
      reopenRef.current?.releasePointerCapture(event.pointerId);
    } catch {
      // Ignore release failures.
    }
  };

  const handleReopenClick = () => {
    // Suppress the click that ends a drag so the ribbon doesn't reopen on drop.
    if (reopenJustDraggedRef.current) {
      reopenJustDraggedRef.current = false;
      return;
    }

    reopenCurrentBanner();
  };

  const isFailed = phase === "failed";
  const isCompleted = phase === "completed";
  const navigationTarget = getGenerationStatusTarget(phase, planId, terminalStatus, source, athleteId);
  const passivePlanTarget = !isActive ? getPassiveLatestJobPlanTarget(latestJob) : null;
  const acknowledgementTarget = isCompleted ? navigationTarget : passivePlanTarget;
  const isAcknowledgementRoute = isGenerationRibbonTargetRedundant(pathname, acknowledgementTarget);
  const ctaLabel = isCompleted && planId ? "View" : navigationTarget ? "Open" : "Refresh";
  const showElapsed = isActive && !isCompleted && !isFailed && startedAtMs !== null;

  const dismissKey =
    !isActive && latestJob?.job_id
      ? latestJobDismissKey(latestJob.job_id)
      : jobId
        ? latestJobDismissKey(jobId)
        : RIBBON_DISMISSED_KEY;

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

      const reduceMotion =
        typeof window !== "undefined" &&
        window.matchMedia("(prefers-reduced-motion: reduce)").matches;

      if (!reduceMotion && typeof navigator !== "undefined" && typeof navigator.vibrate === "function") {
        try {
          navigator.vibrate(20);
        } catch {
          // Vibration unavailable.
        }
      }

      const timer = window.setTimeout(() => setIsCelebrating(false), CELEBRATION_DURATION_MS);
      previousPhaseRef.current = phase;

      return () => window.clearTimeout(timer);
    }

    previousPhaseRef.current = phase;
  }, [phase]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        setIsDismissed(window.localStorage.getItem(dismissKey) === "1");
      } catch {
        setIsDismissed(false);
      }
      setResolvedDismissKey(dismissKey);
    }, 0);

    return () => window.clearTimeout(timer);
  }, [dismissKey]);

  useEffect(() => {
    if (!isAcknowledgementRoute) {
      return;
    }

    try {
      window.localStorage.setItem(dismissKey, "1");
    } catch {}

    const timer = window.setTimeout(() => {
      setIsDismissed(true);
      setResolvedDismissKey(dismissKey);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [dismissKey, isAcknowledgementRoute]);

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
        if (jobId) {
          window.localStorage.removeItem(latestJobDismissKey(jobId));
        }
      } catch {}
    }

    previousGenerationKeyRef.current = generationKey;
  }, [isActive, jobId, startedAtMs]);

  if (!isActive && !latestJob) {
    return null;
  }

  const dismissCurrentBanner = () => {
    setIsDismissed(true);
    setResolvedDismissKey(dismissKey);

    try {
      window.localStorage.setItem(dismissKey, "1");
    } catch {}
  };

  const reopenCurrentBanner = () => {
    setIsDismissed(false);
    setResolvedDismissKey(dismissKey);

    try {
      window.localStorage.removeItem(dismissKey);
    } catch {}
  };

  if (resolvedDismissKey !== dismissKey || isAcknowledgementRoute) {
    return null;
  }

  if (!isActive && latestJob) {
    if (!shouldRenderPassiveLatestJobRibbon(latestJob)) {
      return null;
    }

    if (isDismissed) {
      return null;
    }

    if (latestJob.status === "failed") {
      const failedPlanId = latestJob.plan_id || latestJob.latest_plan_id || null;

      if (latestFailedJobHasOpenablePlan(latestJob) && failedPlanId) {
        const target = getPassiveLatestJobPlanTarget(latestJob) || `/plans/${failedPlanId}`;
        if (isGenerationRibbonTargetRedundant(pathname, target)) {
          return null;
        }

        const isProtectedTriage = isProtectedTriageLatestJob(latestJob);
        return (
          <div className="global-generation-status global-generation-status-completed">
            <Link href={target} className="global-generation-status-main" onClick={dismissCurrentBanner}>
              <div className="global-generation-status-message">
                {isProtectedTriage
                  ? "Plan is held for admin review."
                  : "Your plan is saved and ready."}
              </div>
              <span className="global-generation-status-cta-label">
                {isProtectedTriage ? "Open admin review" : "Open plan"}
              </span>
            </Link>

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

      return (
        <div className="global-generation-status global-generation-status-failed">
          <div className="global-generation-status-main">
            <div className="global-generation-status-content">
              <span className="global-generation-status-text">
                <span className="global-generation-status-message">
                  {humanizeGenerationError(latestJob.error)}
                </span>

                {latestJob.completed_at ? (
                  <span className="global-generation-status-elapsed" suppressHydrationWarning>
                    Completed {new Date(latestJob.completed_at).toLocaleString()}
                  </span>
                ) : null}
              </span>

              {latestJob.can_retry ? (
                <button
                  type="button"
                  className="global-generation-status-cta-label"
                  disabled={isRetryingLatest}
                  onClick={() => {
                    if (!session?.access_token || isRetryingLatest) {
                      return;
                    }

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
              ) : (
                <Link href="/plans" className="global-generation-status-cta-label">
                  Open plan history
                </Link>
              )}
            </div>

            {retryLatestError ? (
              <div className="global-generation-status-message">{retryLatestError}</div>
            ) : null}
          </div>

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

    if (latestJob.status === "review_required" && latestJob.plan_id) {
      const target = getPassiveLatestJobPlanTarget(latestJob) || `/plans/${latestJob.plan_id}`;
      if (isGenerationRibbonTargetRedundant(pathname, target)) {
        return null;
      }

      return (
        <div className="global-generation-status global-generation-status-completed">
          <Link href={target} className="global-generation-status-main" onClick={dismissCurrentBanner}>
            <div className="global-generation-status-message">Review saved plan</div>
            <span className="global-generation-status-cta-label">Open plan</span>
          </Link>

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

    // Protected triage outcomes that live only on the job (no plan_id) —
    // backend reports these as review_required + requires_admin_resume.
    // The user cannot open a plan; the ribbon links to the admin profile
    // for admins, or stays as a static notice otherwise.
    if (
      latestJob.status === "review_required"
      && !latestJob.plan_id
      && isProtectedTriageLatestJob(latestJob)
    ) {
      const adminTarget = latestJob.athlete_id ? `/admin/athletes/${latestJob.athlete_id}` : null;
      const content = (
        <>
          <div className="global-generation-status-message">Plan is held for admin review.</div>
          <span className="global-generation-status-cta-label">
            {adminTarget ? "Open admin review" : "Awaiting admin"}
          </span>
        </>
      );
      return (
        <div className="global-generation-status global-generation-status-completed">
          {adminTarget ? (
            <Link href={adminTarget} className="global-generation-status-main">
              {content}
            </Link>
          ) : (
            <div className="global-generation-status-main">{content}</div>
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

    if (latestJob.status === "completed" && !latestJob.plan_id) {
      const completedPlanId = latestCompletedJobOpenablePlanId(latestJob);

      if (completedPlanId) {
        const target = `/plans/${completedPlanId}`;
        if (isGenerationRibbonTargetRedundant(pathname, target)) {
          return null;
        }

        const isProtectedTriage = isProtectedTriageLatestJob(latestJob);
        return (
          <div className="global-generation-status global-generation-status-completed">
            <Link href={target} className="global-generation-status-main" onClick={dismissCurrentBanner}>
              <div className="global-generation-status-message">
                {isProtectedTriage
                  ? "Plan is held for admin review."
                  : "Your plan is saved and ready."}
              </div>
              <span className="global-generation-status-cta-label">
                {isProtectedTriage ? "Open admin review" : "Open plan"}
              </span>
            </Link>

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

      return (
        <div className="global-generation-status global-generation-status-failed">
          <div className="global-generation-status-main">
            <div className="global-generation-status-content">
              <span className="global-generation-status-text">
                <span className="global-generation-status-message">
                  Your plan finished but could not be opened. Support can recover it.
                </span>
              </span>

              <Link href="/plans" className="global-generation-status-cta-label">
                Open plan history
              </Link>
            </div>
          </div>

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
  }

  const canNavigateToPlan = Boolean(navigationTarget);
  const elapsedLabel = showElapsed && startedAtMs !== null ? formatElapsed(now - startedAtMs) : null;
  const className = [
    "global-generation-status",
    isFailed ? "global-generation-status-failed" : "",
    isCompleted ? "global-generation-status-completed" : "",
    isCelebrating ? "global-generation-status-celebrating" : "",
  ]
    .filter(Boolean)
    .join(" ");

  if (!statusMessage && !phase && !navigationTarget) {
    return null;
  }

  if (isFailed && !isDismissed) {
    // The /generate screen already owns the full failure story; a second
    // ribbon on top of it is noise.
    if (pathname === "/generate") {
      return null;
    }

    return (
      <div className="global-generation-status global-generation-status-failed">
        <div className="global-generation-status-main">
          <div className="global-generation-status-content">
            <span className="global-generation-status-text">
              <span className="global-generation-status-message">{statusMessage}</span>
            </span>

            {/*
              A stalled build is still queued/running server-side, so cancelling
              it is the action that changes something — the cancel endpoint
              rejects an already-terminal job. A genuinely failed job gets a
              retry instead. Neither state offers a "tap to refresh": re-reading
              a dead job cannot revive it, and swapping the ribbon back to a
              live-looking status is exactly what made a failure look like a
              build in progress.
            */}
            {jobId && isStalled ? (
              <button
                type="button"
                className="global-generation-status-cta-label"
                disabled={isCancelling}
                onClick={() => {
                  if (!session?.access_token || isCancelling) {
                    return;
                  }

                  setCancelError(null);
                  setIsCancelling(true);

                  void cancelGenerationJob(session.access_token, jobId)
                    .then(() => refreshStatus())
                    .catch(() => setCancelError("Cancel failed. Try again."))
                    .finally(() => setIsCancelling(false));
                }}
              >
                {isCancelling ? "Stopping..." : "Stop build"}
              </button>
            ) : null}

            {jobId && !isStalled ? (
              <button
                type="button"
                className="global-generation-status-cta-label"
                disabled={isRetryingLatest}
                onClick={() => {
                  if (!session?.access_token || isRetryingLatest) {
                    return;
                  }

                  setRetryLatestError(null);
                  setIsRetryingLatest(true);

                  void retryGenerationJob(session.access_token, jobId)
                    .then(() => refreshStatus())
                    .catch(() => setRetryLatestError("Retry failed. Open Generate and try again."))
                    .finally(() => setIsRetryingLatest(false));
                }}
              >
                {isRetryingLatest ? "Retrying..." : "Retry"}
              </button>
            ) : null}
          </div>

          {cancelError ? <div className="global-generation-status-message">{cancelError}</div> : null}
          {retryLatestError ? (
            <div className="global-generation-status-message">{retryLatestError}</div>
          ) : null}
        </div>

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

  if (isDismissed) {
    return (
      <button
        ref={reopenRef}
        type="button"
        className="global-generation-status-reopen"
        aria-label="Show generation ribbon"
        style={
          reopenPos
            ? { left: reopenPos.x, top: reopenPos.y, right: "auto", bottom: "auto" }
            : undefined
        }
        onPointerDown={handleReopenPointerDown}
        onPointerMove={handleReopenPointerMove}
        onPointerUp={handleReopenPointerUp}
        onPointerCancel={handleReopenPointerUp}
        onClick={handleReopenClick}
      >
        {isFailed ? "Show build error" : "Show plan build"}
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
          <span className="global-generation-status-arrow" aria-hidden="true">
            →
          </span>
        </span>
      </div>

      {!isFailed && !isCompleted ? (
        <div className="global-generation-status-rail" aria-hidden="true">
          <span className="global-generation-status-line" />
        </div>
      ) : null}

      {isCelebrating ? (
        <span className="global-generation-status-celebrate-glow" aria-hidden="true" />
      ) : null}
    </>
  );

  return (
    <div className={className}>
      {canNavigateToPlan && navigationTarget ? (
        <Link
          href={navigationTarget}
          className="global-generation-status-main"
          onClick={isCompleted ? dismissCurrentBanner : undefined}
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
          aria-label={
            isCompleted
              ? "Plan completed. Tap to refresh status."
              : "Generation in progress. Tap to refresh status."
          }
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
