"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
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

export function GlobalGenerationStatus() {
  const { isActive, statusMessage, phase, planId, startedAtMs } = useGenerationStatus();
  const [now, setNow] = useState(() => Date.now());

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

  if (!isActive) {
    return null;
  }

  const href = isCompleted && planId ? `/plans/${planId}` : "/generate";
  const elapsedLabel = showElapsed && startedAtMs !== null ? formatElapsed(now - startedAtMs) : null;

  return (
    <Link
      href={href}
      className={`global-generation-status${isFailed ? " global-generation-status-failed" : ""}${isCompleted ? " global-generation-status-completed" : ""}`}
      aria-label={isCompleted ? "Plan ready. Tap to view." : "Generation in progress. Tap to view details."}
    >
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
          <span className="global-generation-status-cta-label">{isCompleted ? "View" : "Open"}</span>
          <span className="global-generation-status-arrow" aria-hidden="true">→</span>
        </span>
      </div>
      {!isFailed && !isCompleted && (
        <div className="global-generation-status-rail" aria-hidden="true">
          <span className="global-generation-status-line" />
        </div>
      )}
    </Link>
  );
}
