"use client";

import { useEffect, useState } from "react";

import { describeGenerationFailure, GENERATION_FAILURE_ACTION_LABELS } from "@/lib/generation-failure";
import type { GenerationFailureKind } from "@/lib/generation-failure";
import type { GenerationUiPhase } from "@/lib/generation-controller";
import { getPublicMilestoneIndex, getPublicProgress, PUBLIC_CAMP_MILESTONES } from "@/lib/public-generation-progress";
import type { ProgressMilestone } from "@/lib/types";
import styles from "./public-generation-theme.module.css";
import { useTranslations as useAppTranslations } from "next-intl";
import { translateUiText } from "@/i18n/ui-text";


type Props = {
  phase: GenerationUiPhase;
  error?: string | null;
  failureKind?: GenerationFailureKind | null;
  milestones?: ProgressMilestone[];
  startedAtMs?: number | null;
  jobId?: string | null;
  readyToOpen?: boolean;
  canRetry?: boolean;
  onRetry?: (() => void) | null;
  onReturnToWorkspace?: (() => void) | null;
  onRefineIntake?: (() => void) | null;
};

const PROGRESS_STORAGE_PREFIX = "unlxck:public-generation-progress:";

function readSavedProgress(jobId: string | null): number {
  if (!jobId || typeof window === "undefined") return 0;
  const value = Number(window.localStorage.getItem(`${PROGRESS_STORAGE_PREFIX}${jobId}`));
  return Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0;
}

export function PublicGenerationScreen({ phase, error = null, failureKind = null, milestones = [], startedAtMs = null, jobId = null, readyToOpen = false, canRetry = false, onRetry = null, onReturnToWorkspace = null, onRefineIntake = null }: Props) {
    const appText = useAppTranslations("AppText");
  const [now, setNow] = useState(() => Date.now());
  const [progressFloor, setProgressFloor] = useState(() => readSavedProgress(jobId));
  const terminal = ["failed", "review_paused", "already_generated"].includes(phase);
  useEffect(() => {
    if (terminal || phase === "finalizing") return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [phase, terminal]);

  useEffect(() => {
    setProgressFloor(readSavedProgress(jobId));
  }, [jobId]);

  const activeIndex = getPublicMilestoneIndex(phase, milestones);
  const progress = getPublicProgress(phase, milestones, startedAtMs, now, progressFloor, readyToOpen);
  const failure = phase === "failed" ? describeGenerationFailure(failureKind, error) : null;
  const takingLonger = !terminal && phase !== "finalizing" && startedAtMs !== null && now - startedAtMs > 10 * 60_000;

  useEffect(() => {
    if (!jobId || progress <= progressFloor) return;
    setProgressFloor(progress);
    window.localStorage.setItem(`${PROGRESS_STORAGE_PREFIX}${jobId}`, String(progress));
  }, [jobId, progress, progressFloor]);

  if (failure) {
    return <section className={`public-build public-build-terminal ${styles.theme}`}><p className="public-build-kicker">{appText("text_067f91a71e1b")}</p><h1>{failure.headline}</h1><p>{failure.detail}</p><div className="public-build-actions">{canRetry && onRetry ? <button className="cta" onClick={onRetry}>{GENERATION_FAILURE_ACTION_LABELS.retry}</button> : null}{onRefineIntake ? <button className="cta ghost" onClick={onRefineIntake}>{appText("text_419308670222")}</button> : null}{onReturnToWorkspace ? <button className="cta ghost" onClick={onReturnToWorkspace}>{appText("text_02e565ef63bc")}</button> : null}</div></section>;
  }

  return (
    <section className={`public-build ${styles.theme}`}>
      <header><p className="public-build-kicker">{appText("text_a61e27f94b92")}</p><h1>{appText("text_84f748774480")}</h1><p className="public-build-estimate">{appText("text_04d1e6bd425a")}</p></header>
      <div className="public-build-mark" aria-hidden="true"><span className="public-build-ring public-build-ring-one"/><span className="public-build-ring public-build-ring-two"/><span className="public-build-core">{appText("text_a25513c7e0f6")}</span></div>
      <div className="public-build-status" aria-live="polite"><strong>{takingLonger ? appText("text_1a5787cd1c50") : translateUiText(appText, PUBLIC_CAMP_MILESTONES[activeIndex].title)}</strong><span>{takingLonger ? appText("text_66965148c39a") : translateUiText(appText, PUBLIC_CAMP_MILESTONES[activeIndex].detail)}</span></div>
      <div className="public-build-bar" role="progressbar" aria-label={appText("text_88ba6de33e7c")} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.floor(progress)}><span style={{ width: `${progress}%` }}/></div>
      <ol className="public-build-milestones">
        {PUBLIC_CAMP_MILESTONES.map((item, index) => { const state = index < activeIndex || (readyToOpen && index <= activeIndex) ? "complete" : index === activeIndex ? "active" : "future"; return <li key={item.code} className={`public-build-milestone public-build-milestone-${state}`}><span>{state === "complete" ? "✓" : ""}</span><div><strong>{translateUiText(appText, item.title)}</strong><small>{translateUiText(appText, item.detail)}</small></div></li>; })}
      </ol>
      <p className="public-build-reassurance"><strong>{appText("text_f681256601de")}</strong> {appText("text_d4ed7d31e032")}</p>
    </section>
  );
}
