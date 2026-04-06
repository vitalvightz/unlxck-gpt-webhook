"use client";

import Link from "next/link";
import { useGenerationStatus } from "./generation-status-provider";

export function GlobalGenerationStatus() {
  const { isActive, statusMessage, phase } = useGenerationStatus();

  if (!isActive) {
    return null;
  }

  const isFailed = phase === "failed";

  return (
    <Link 
      href="/generate" 
      className={`global-generation-status${isFailed ? " global-generation-status-failed" : ""}`}
      aria-label="Generation in progress. Click to view details."
    >
      <div className="global-generation-status-content">
        <span className="global-generation-status-indicator" aria-hidden="true">
          <span className="global-generation-status-pulse" />
        </span>
        <span className="global-generation-status-text">{statusMessage}</span>
        <span className="global-generation-status-arrow" aria-hidden="true">→</span>
      </div>
      {!isFailed && (
        <div className="global-generation-status-rail" aria-hidden="true">
          <span className="global-generation-status-line" />
        </div>
      )}
    </Link>
  );
}
