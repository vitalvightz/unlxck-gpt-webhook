"use client";

import Link from "next/link";
import { useGenerationStatus } from "./generation-status-provider";

export function GlobalGenerationStatus() {
  const { isActive, statusMessage, phase, planId } = useGenerationStatus();

  if (!isActive) {
    return null;
  }

  const isFailed = phase === "failed";
  const isCompleted = phase === "completed";

  // Link to plan when completed, otherwise to generate page
  const href = isCompleted && planId ? `/plans/${planId}` : "/generate";

  return (
    <Link 
      href={href}
      className={`global-generation-status${isFailed ? " global-generation-status-failed" : ""}${isCompleted ? " global-generation-status-completed" : ""}`}
      aria-label={isCompleted ? "Plan ready! Click to view." : "Generation in progress. Click to view details."}
    >
      <div className="global-generation-status-content">
        <span className="global-generation-status-indicator" aria-hidden="true">
          {isCompleted ? (
            <span className="global-generation-status-check">&#10003;</span>
          ) : (
            <span className="global-generation-status-pulse" />
          )}
        </span>
        <span className="global-generation-status-text">{statusMessage}</span>
        <span className="global-generation-status-arrow" aria-hidden="true">
          {isCompleted ? "View →" : "→"}
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
