"use client";

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

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
    background:
      "radial-gradient(circle at top left, rgba(181,18,43,.16), transparent 30%), linear-gradient(180deg, #080809, #0d0f12 55%, #09090a)",
    color: "#f5f7fa",
    fontFamily: "Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  },
  main: {
    boxSizing: "border-box" as const,
    width: "min(100%, 520px)",
    padding: "clamp(28px, 7vw, 48px)",
    border: "1px solid #2a2f37",
    borderRadius: 24,
    background: "linear-gradient(180deg, rgba(21,24,28,.98), rgba(13,15,18,.98))",
  },
  label: {
    margin: "0 0 10px",
    color: "#ff8da1",
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
    border: "1px solid #ca1834",
    borderRadius: 10,
    background: "#b5122b",
    color: "#fff",
    font: "700 15px/1 system-ui, sans-serif",
    cursor: "pointer",
  },
};

export default function GlobalError({ error }: { error: Error & { digest?: string } }) {
  const connectionProblem = isNetworkFailure(error) || isBrowserOffline();

  useEffect(() => {
    if (!connectionProblem) {
      Sentry.captureException(error);
    }
  }, [connectionProblem, error]);

  useEffect(() => {
    if (!connectionProblem) return;
    const onOnline = () => window.location.reload();
    window.addEventListener("online", onOnline);
    return () => window.removeEventListener("online", onOnline);
  }, [connectionProblem]);

  return (
    <html lang="en" style={{ colorScheme: "dark" }}>
      <body style={styles.body}>
        <main style={styles.main} role="alert">
          <p style={styles.label}>{connectionProblem ? "Connection offline" : "Something broke"}</p>
          <h1 style={styles.h1}>
            {connectionProblem ? "UNLXCK can’t connect right now." : "UNLXCK hit a snag."}
          </h1>
          <p style={styles.p}>
            {connectionProblem
              ? "Your plan and logs are safe on our side. Reconnect and we’ll bring you straight back."
              : "Your data is safe. Reload to get back to your training."}
          </p>
          <button type="button" style={styles.button} onClick={() => window.location.reload()}>
            {connectionProblem ? "Retry connection" : "Reload UNLXCK"}
          </button>
        </main>
      </body>
    </html>
  );
}
