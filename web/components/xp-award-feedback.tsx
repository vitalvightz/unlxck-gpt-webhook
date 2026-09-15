"use client";

import Link from "next/link";
import { useEffect } from "react";

import { useToast } from "@/components/toast-provider";
import { useXp } from "@/components/xp-provider";
import { useTranslations as useAppTranslations } from "next-intl";


export function XpAwardFeedback() {
    const appText = useAppTranslations("AppText");
  const { feedback, dismissFeedback } = useXp();
  const { showToast } = useToast();

  useEffect(() => {
    if (!feedback || feedback.kind !== "routine") return;
    showToast(`+${feedback.amount} XP: ${feedback.label}`, {
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
        aria-label={appText("text_d285ff223cf8")}
      >
        {appText("text_8db71ed28b0f")}</button>
      <p className="xp-level-up-kicker">{appText("text_ec89a5737cd9")}</p>
      <h2 id="xp-level-up-title">
        {appText("text_d81674b2bdd5")} {feedback.level}{appText("text_e7ac0786668e")} {feedback.title.toUpperCase()}
      </h2>
      <p id="xp-level-up-message">{feedback.message}</p>
      <Link href="/progress" onClick={dismissFeedback}>
        {appText("text_c2e39c2cee78")}</Link>
    </section>
  );
}
