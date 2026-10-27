"use client";

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

import { useConnectionRecovery } from "@/lib/use-connection-recovery";

import { isBrowserOffline, isNetworkFailure } from "@/lib/connectivity";

// Last-resort boundary: it replaces the root layout, so no global CSS, fonts
// or providers are available here. Everything is inline and self-contained,
// mirroring public/offline.html so a crash still looks like UNLXCK.
const styles = {
  body: {
    margin: 0,
    minHeight: "100dvh",
    display: "grid",
    placeItems: "center",
    padding: "28px 20px",
    background: "#080809",
    color: "#f5f7fa",
    fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  },
  main: {
    boxSizing: "border-box" as const,
    width: "min(100%, 400px)",
    padding: "32px",
    border: "1px solid #ffffff1c",
    borderRadius: 16,
    background: "#101012",
    boxShadow: "0 24px 64px #0008",
  },
  label: {
    margin: "0 0 10px",
    color: "#b2b2ba",
    font: "600 11px/1.2 ui-monospace, Menlo, Consolas, monospace",
    letterSpacing: ".18em",
    textTransform: "uppercase" as const,
  },
  h1: { margin: 0, fontSize: "clamp(32px, 8vw, 48px)", lineHeight: 1, letterSpacing: "-.04em" },
  p: { margin: "20px 0 0", color: "#a7adb7", fontSize: 16, lineHeight: 1.6 },
  button: {
    width: "100%",
    minHeight: 52,
    marginTop: 30,
    border: "1px solid #e04451",
    borderRadius: 7,
    background: "#b5122b",
    color: "#fff",
    font: "700 15px/1 system-ui, sans-serif",
    cursor: "pointer",
  },
};

export default function GlobalError({ error }: { error: Error & { digest?: string } }) {
  const connectionProblem = isNetworkFailure(error) || isBrowserOffline();
  const { retrying, retryFailed, retryConnection } = useConnectionRecovery(connectionProblem);

  useEffect(() => {
    if (!connectionProblem) {
      Sentry.captureException(error);
    }
  }, [connectionProblem, error]);

  return (
    <html lang="en" style={{ colorScheme: "dark" }}>
      <body style={styles.body}>
        <main style={styles.main} role="alert">
          <p style={styles.label}>{connectionProblem ? "Connection interrupted" : "Something broke"}</p>
          <h1 style={styles.h1}>
            {connectionProblem ? "UNLXCK can’t connect right now." : "UNLXCK hit a snag."}
          </h1>
          <p style={styles.p}>
            {connectionProblem
              ? "Your plan and logs are safe. Reconnect to carry on."
              : "Your data is safe. Reload to get back to your training."}
          </p>
          {retryFailed ? <p style={styles.p} role="status">Still can’t reach UNLXCK. Try again shortly.</p> : null}
          <button type="button" style={styles.button} disabled={retrying} onClick={() => connectionProblem ? void retryConnection() : window.location.reload()}>
            {retrying ? "Checking connection…" : connectionProblem ? "Retry connection" : "Reload UNLXCK"}
          </button>
        </main>
      </body>
    </html>
  );
}
