"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
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

export function GlobalGenerationStatus() {
  const { isActive, statusMessage, phase, planId, startedAtMs, refreshStatus } = useGenerationStatus();
  const router = useRouter();
  const [now, setNow] = useState(() => Date.now());
  const [isCelebrating, setIsCelebrating] = useState(false);
  const previousPhaseRef = useRef(phase);

  const isFailed = phase === "failed";
  const isCompleted = phase === "completed";
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

  if (!isActive) {
    return null;
  }

  const canNavigateToPlan = isCompleted && Boolean(planId);
  const elapsedLabel = showElapsed && startedAtMs !== null ? formatElapsed(now - startedAtMs) : null;
  const className = [
    "global-generation-status",
    isFailed ? "global-generation-status-failed" : "",
    isCompleted ? "global-generation-status-completed" : "",
    isCelebrating ? "global-generation-status-celebrating" : "",
  ].filter(Boolean).join(" ");

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
          <span className="global-generation-status-cta-label">{canNavigateToPlan ? "View" : "Refresh"}</span>
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

  if (canNavigateToPlan && planId) {
    return (
      <Link
        href={`/plans/${planId}`}
        className={className}
        aria-label="Plan ready. Tap to view."
      >
        {content}
      </Link>
    );
  }

  return (
    <button
      type="button"
      className={className}
      aria-label={isFailed ? "Plan failed. Tap to refresh status." : "Generation in progress. Tap to refresh status."}
      onClick={() => {
        if (!isFailed) {
          router.push("/");
          return;
        }
        refreshStatus();
      }}
    >
      {content}
    </button>
  );
}
