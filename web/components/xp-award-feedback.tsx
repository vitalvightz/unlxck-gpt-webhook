"use client";

import Link from "next/link";
import { useEffect } from "react";

import { useToast } from "@/components/toast-provider";
import { useXp } from "@/components/xp-provider";

export function XpAwardFeedback() {
  const { feedback, dismissFeedback } = useXp();
  const { showToast } = useToast();

  useEffect(() => {
    if (!feedback || feedback.kind !== "routine") return;
    showToast(`+${feedback.amount} XP — ${feedback.label}`, {
      tone: "success",
      durationMs: 4_500,
    });
    dismissFeedback();
  }, [dismissFeedback, feedback, showToast]);

  useEffect(() => {
    if (!feedback || feedback.kind !== "level_up") return;
    const timer = window.setTimeout(dismissFeedback, 7_000);
    return () => window.clearTimeout(timer);
  }, [dismissFeedback, feedback]);

  if (!feedback || feedback.kind !== "level_up") return null;

  return (
    <section
      className="xp-level-up-feedback"
      role="dialog"
      aria-modal="false"
      aria-labelledby="xp-level-up-title"
      aria-describedby="xp-level-up-message"
    >
      <button
        type="button"
        className="xp-level-up-dismiss"
        onClick={dismissFeedback}
        aria-label="Dismiss level-up message"
      >
        ×
      </button>
      <p className="xp-level-up-kicker">LEVEL UP</p>
      <h2 id="xp-level-up-title">
        LEVEL {feedback.level} — {feedback.title.toUpperCase()}
      </h2>
      <p id="xp-level-up-message">{feedback.message}</p>
      <Link href="/progress" onClick={dismissFeedback}>
        View progress
      </Link>
    </section>
  );
}
