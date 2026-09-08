"use client";

import { useEffect, useState } from "react";

import { describeGenerationFailure, GENERATION_FAILURE_ACTION_LABELS } from "@/lib/generation-failure";
import type { GenerationFailureKind } from "@/lib/generation-failure";
import type { GenerationUiPhase } from "@/lib/generation-controller";
import { getPublicMilestoneIndex, getPublicProgress, PUBLIC_CAMP_MILESTONES } from "@/lib/public-generation-progress";
import type { ProgressMilestone } from "@/lib/types";

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
    return <section className="public-build public-build-terminal"><p className="public-build-kicker">Build stopped</p><h1>{failure.headline}</h1><p>{failure.detail}</p><div className="public-build-actions">{canRetry && onRetry ? <button className="cta" onClick={onRetry}>{GENERATION_FAILURE_ACTION_LABELS.retry}</button> : null}{onRefineIntake ? <button className="cta ghost" onClick={onRefineIntake}>Fix my intake</button> : null}{onReturnToWorkspace ? <button className="cta ghost" onClick={onReturnToWorkspace}>Return to workspace</button> : null}</div></section>;
  }

  return (
    <section className="public-build">
      <header><p className="public-build-kicker">Fight camp build</p><h1>YOUR CAMP IS TAKING SHAPE</h1><p className="public-build-estimate">Usually 3–10 minutes</p></header>
      <div className="public-build-mark" aria-hidden="true"><span className="public-build-ring public-build-ring-one"/><span className="public-build-ring public-build-ring-two"/><span className="public-build-core">U</span></div>
      <div className="public-build-status" aria-live="polite"><strong>{takingLonger ? "Taking longer than usual" : PUBLIC_CAMP_MILESTONES[activeIndex].title}</strong><span>{takingLonger ? "Final checks are still in progress." : PUBLIC_CAMP_MILESTONES[activeIndex].detail}</span></div>
      <div className="public-build-bar" role="progressbar" aria-label="Camp build progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.floor(progress)}><span style={{ width: `${progress}%` }}/></div>
      <ol className="public-build-milestones">
        {PUBLIC_CAMP_MILESTONES.map((item, index) => { const state = index < activeIndex || (readyToOpen && index <= activeIndex) ? "complete" : index === activeIndex ? "active" : "future"; return <li key={item.code} className={`public-build-milestone public-build-milestone-${state}`}><span>{state === "complete" ? "✓" : ""}</span><div><strong>{item.title}</strong><small>{item.detail}</small></div></li>; })}
      </ol>
      <p className="public-build-reassurance"><strong>Safe to leave.</strong> Your build continues in the background.</p>
    </section>
  );
}
