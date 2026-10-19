"use client";

import * as Sentry from "@sentry/nextjs";
import { useEffect, useState } from "react";

import { isBrowserOffline, isNetworkFailure } from "@/lib/connectivity";

/**
 * Route-level crash boundary. Without it any render error — most commonly a
 * code-split chunk that could not download because the connection dropped
 * mid-navigation — fell through to Next's unbranded "Application error" page.
 */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const connectionProblem = isNetworkFailure(error) || isBrowserOffline();
  const [isRetrying, setIsRetrying] = useState(false);

  useEffect(() => {
    // Connection drops are expected field conditions, not bugs.
    if (!connectionProblem) {
      Sentry.captureException(error);
    }
  }, [connectionProblem, error]);

  useEffect(() => {
    if (!connectionProblem) return;
    // Reconnecting recovers on its own: a full reload re-fetches the chunk
    // that failed, which reset() alone cannot do.
    const onOnline = () => window.location.reload();
    window.addEventListener("online", onOnline);
    return () => window.removeEventListener("online", onOnline);
  }, [connectionProblem]);

  function retry() {
    setIsRetrying(true);
    if (connectionProblem) {
      window.location.reload();
      return;
    }
    reset();
    setIsRetrying(false);
  }

  return (
    <section className="panel loading-card" role="alert">
      <p className="kicker">{connectionProblem ? "Connection offline" : "Something broke"}</p>
      <h1>{connectionProblem ? "Lost the connection mid-round." : "This screen hit a snag."}</h1>
      <p className="muted">
        {connectionProblem
          ? "Your plan and logs are safe on our side. Reconnect and we’ll pick up where you left off."
          : "Your data is safe. Try again — if it keeps happening, head back to your dashboard."}
      </p>
      <div className="hero-actions">
        <button type="button" className="cta" onClick={retry} disabled={isRetrying}>
          {isRetrying ? "Unlxcking…" : "Try again"}
        </button>
        {/* Plain anchor: a full navigation is the reliable path out of a broken route. */}
        <a href="/" className="secondary-button">
          Back to dashboard
        </a>
      </div>
    </section>
  );
}
