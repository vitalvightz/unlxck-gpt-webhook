"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
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

export function getGenerationStatusTarget(
  phase: string | null,
  planId: string | null,
  terminalStatus: "completed" | "review_required" | null,
): `/generate` | `/plans/${string}` | `/plans/${string}?review_required=1` | null {
  if (phase === "queued" || phase === "running" || phase === "finalizing") {
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
  const { isActive, statusMessage, phase, planId, terminalStatus, startedAtMs, refreshStatus } = useGenerationStatus();
  const [now, setNow] = useState(() => Date.now());
  const [isCelebrating, setIsCelebrating] = useState(false);
  const [isDismissed, setIsDismissed] = useState(false);
  const previousPhaseRef = useRef(phase);

  const isFailed = phase === "failed";
  const isCompleted = phase === "completed";
  const navigationTarget = getGenerationStatusTarget(phase, planId, terminalStatus);
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
      setIsDismissed(window.localStorage.getItem(RIBBON_DISMISSED_KEY) === "1");
    } catch {
      setIsDismissed(false);
    }
  }, []);

  if (!isActive) {
    return null;
  }

  const canNavigateToPlan = Boolean(navigationTarget);
  const elapsedLabel = showElapsed && startedAtMs !== null ? formatElapsed(now - startedAtMs) : null;
  const className = [
    "global-generation-status",
    isFailed ? "global-generation-status-failed" : "",
    isCompleted ? "global-generation-status-completed" : "",
    isCelebrating ? "global-generation-status-celebrating" : "",
  ].filter(Boolean).join(" ");

  const dismissButton = (
    <button
      type="button"
      className="global-generation-status-dismiss"
      aria-label="Hide generation ribbon"
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        setIsDismissed(true);
        try {
          window.localStorage.setItem(RIBBON_DISMISSED_KEY, "1");
        } catch {}
      }}
    >
      ×
    </button>
  );

  if (isDismissed) {
    return (
      <button
        type="button"
        className="global-generation-status-reopen"
        aria-label="Show generation ribbon"
        onClick={() => {
          setIsDismissed(false);
          try {
            window.localStorage.removeItem(RIBBON_DISMISSED_KEY);
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

  if (canNavigateToPlan && navigationTarget) {
    return (
      <Link
        href={navigationTarget}
        className={className}
        aria-label={
          isCompleted
            ? "Plan ready. Tap to view."
            : "Generation in progress. Tap to open generation status."
        }
      >
        {dismissButton}
        {content}
      </Link>
    );
  }

  return (
    <button
      type="button"
      className={className}
      aria-label={isFailed ? "Plan failed. Tap to refresh status." : isCompleted ? "Plan completed. Tap to refresh status." : "Generation in progress. Tap to refresh status."}
      onClick={() => {
        refreshStatus();
      }}
    >
      {dismissButton}
      {content}
    </button>
  );
}
