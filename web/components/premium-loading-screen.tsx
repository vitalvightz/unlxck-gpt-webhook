"use client";

import { useEffect, useState } from "react";

import { GenerationProgressMilestones } from "@/components/generation-progress-milestones";
import { StageOnePreviewCard } from "@/components/stage-one-preview-card";
import type { GenerationUiPhase } from "@/lib/generation-controller";
import {
  describeGenerationFailure,
  GENERATION_FAILURE_ACTION_LABELS,
  type GenerationFailureAction,
  type GenerationFailureKind,
} from "@/lib/generation-failure";
import { formatGenerationElapsedLabel } from "@/lib/generation-elapsed";
import {
  formatMilestoneDurationLabel,
  resolveMilestoneDurations,
} from "@/lib/generation-milestone-duration";
import { buildStageOnePreview } from "@/lib/stage-one-preview";
import type { PlanRequest, ProgressMilestone } from "@/lib/types";
import { useTranslations as useAppTranslations } from "next-intl";


const WORKFLOW_STEPS = [
  {
    key: "submitting",
    title: "Save intake",
    detail: "Store your answers before the plan build starts.",
  },
  {
    key: "queued",
    title: "Prepare build",
    detail: "Hold your place while the planner gets ready.",
  },
  {
    key: "running",
    title: "Build camp",
    detail: "Turn the saved intake into a structured fight-camp plan.",
  },
  {
    key: "reconnecting",
    title: "Reconnect",
    detail: "Restore the same saved build if the browser or network drops.",
  },
  {
    key: "finalizing",
    title: "Open plan",
    detail: "Run final checks and open the saved plan.",
  },
] as const;

const PHASE_ORDER: Record<GenerationUiPhase, number> = {
  submitting: 0,
  queued: 1,
  running: 2,
  reconnecting: 3,
  finalizing: 4,
  already_generated: 4,
  review_paused: 4,
  failed: 4,
};

export const PHASE_CONTENT: Record<
  GenerationUiPhase,
  {
    eyebrow: string;
    title: string;
    copy: string;
    chip: string;
    statusFallback: string;
    reassurance: string;
    buildState: string;
  }
> = {
  submitting: {
    eyebrow: "Plan build",
    title: "Saving your intake.",
    copy: "We are storing your answers first so the plan can be built from the exact setup you just entered.",
    chip: "Submitting",
    statusFallback: "Saving your intake now.",
    reassurance: "Safe to leave and return. This workspace reconnects to the same saved plan build instead of starting over.",
    buildState: "Saving",
  },
  queued: {
    eyebrow: "Plan build",
    title: "Intake saved. Planner is next.",
    copy: "Your setup is safely saved. The next step is building the camp plan from that saved intake.",
    chip: "Queued",
    statusFallback: "Your saved intake is queued for planning.",
    reassurance: "Safe to leave and return. This workspace reconnects to the same saved plan build instead of starting over.",
    buildState: "Queued",
  },
  running: {
    eyebrow: "Plan build",
    title: "Building your fight camp.",
    copy: "The planner is shaping the camp structure, checking safety constraints, and preparing the athlete-facing plan.",
    chip: "Running",
    statusFallback: "Your saved plan build is in progress.",
    reassurance: "Safe to leave and return. This workspace reconnects to the same saved plan build instead of starting over.",
    buildState: "Building",
  },
  reconnecting: {
    eyebrow: "Connection watch",
    title: "Reconnecting to the same plan build.",
    copy: "The saved build is still intact. We are only restoring the browser link so this page can keep watching it.",
    chip: "Reconnecting",
    statusFallback: "Reconnecting to the saved plan build now.",
    reassurance: "Safe to leave and return. This workspace reconnects to the same saved plan build instead of starting over.",
    buildState: "Reconnecting",
  },
  finalizing: {
    eyebrow: "Final checks",
    title: "Plan ready. Opening workspace.",
    copy: "The plan is complete. We are closing the final checks before it opens inside your workspace.",
    chip: "Finalizing",
    statusFallback: "Final checks passed. Opening your saved plan.",
    reassurance: "The saved plan is ready. This page is only closing the final handoff before your workspace opens.",
    buildState: "Opening",
  },
  already_generated: {
    eyebrow: "Plan already exists",
    title: "This intake already has a generated plan.",
    copy: "Open the existing plan or refine the intake to create a new version.",
    chip: "Already generated",
    statusFallback: "This intake already has a generated plan.",
    reassurance: "No new duplicate was created.",
    buildState: "Existing plan",
  },
  review_paused: {
    eyebrow: "Planning paused",
    title: "Admin review required",
    copy: "Stage 1 triage flagged this intake for admin review before generation can continue. No plan was created; nothing was lost. The admin team can approve and resume from their console.",
    chip: "Admin review",
    statusFallback: "Planning paused. Admin review is required before generation can continue.",
    reassurance: "Your intake is saved and visible to admins. You'll be notified when the plan is ready.",
    buildState: "Paused",
  },
  failed: {
    eyebrow: "Generation stopped",
    // Overridden per failure kind by describeGenerationFailure; these stay as
    // the fallback for a failure the classifier could not name.
    title: "Your plan build stopped before it finished.",
    copy: "The saved intake did not reach an openable plan state.",
    chip: "Stopped",
    statusFallback: "The plan build stopped.",
    reassurance: "Your intake is still saved. No half-finished plan was kept.",
    buildState: "Stopped",
  },
};

const ESTIMATE_COPY = "Plan build has started. You can leave and return later; the saved build keeps running.";

interface PremiumLoadingScreenProps {
  phase: GenerationUiPhase;
  error?: string | null;
  statusMessage?: string | null;
  startedAtMs?: number | null;
  // Backend-derived instant the job stopped. Once set, every clock on this
  // screen — total elapsed and the active stage's duration — reads from it
  // instead of Date.now().
  endedAtMs?: number | null;
  milestones?: ProgressMilestone[];
  intake?: PlanRequest | null;
  failureKind?: GenerationFailureKind | null;
  onRetry?: (() => void) | null;
  canRetry?: boolean;
  onOpenPlanHistory?: (() => void) | null;
  onReturnToWorkspace?: (() => void) | null;
  onRefineIntake?: (() => void) | null;
}

export function PremiumLoadingScreen({
  phase,
  error = null,
  statusMessage = null,
  startedAtMs = null,
  endedAtMs = null,
  milestones = [],
  intake = null,
  failureKind = null,
  onRetry = null,
  canRetry = false,
  onOpenPlanHistory = null,
  onReturnToWorkspace = null,
  onRefineIntake = null,
}: PremiumLoadingScreenProps) {
    const appText = useAppTranslations("AppText");
  const phaseContent = PHASE_CONTENT[phase];
  const activeIndex = PHASE_ORDER[phase];
  const isFailed = phase === "failed";
  const isTerminalNonProgress = isFailed || phase === "already_generated" || phase === "review_paused";
  const failure = isFailed ? describeGenerationFailure(failureKind, error) : null;
  const failureHandlers: Record<GenerationFailureAction, (() => void) | null> = {
    retry: canRetry ? onRetry : null,
    refine_intake: onRefineIntake,
    plan_history: onOpenPlanHistory,
    workspace: onReturnToWorkspace,
  };
  // A failed build must never leave the athlete without a way out, so the
  // workspace exit is appended whenever the classified actions do not already
  // include it.
  const failureActions: GenerationFailureAction[] = failure
    ? Array.from(new Set<GenerationFailureAction>([failure.primary, ...failure.secondary, "workspace"]))
        .filter((action) => failureHandlers[action] !== null)
    : [];
  // A stopped build still says how long it ran. The reading freezes because
  // `endedAtMs` replaces `now` in the subtraction, not because it is hidden —
  // hiding it is what left the screen with no account of the time it spent.
  const showElapsed = startedAtMs !== null;
  const isElapsedRunning = showElapsed && endedAtMs === null;
  const [now, setNow] = useState(() => Date.now());
  const stageOnePreview = isTerminalNonProgress ? null : buildStageOnePreview(intake, milestones);

  useEffect(() => {
    if (!isElapsedRunning) {
      return;
    }
    setNow(Date.now());
    const interval = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [isElapsedRunning]);

  const elapsedLabel = showElapsed
    ? formatGenerationElapsedLabel({ startedAtMs, endedAtMs, nowMs: now })
    : null;
  const showMilestones = phase !== "submitting" && milestones.length > 0;
  // Durations are resolved across the whole feed before slicing, so the last
  // visible row still knows which milestone actually ended it.
  const milestoneDurations = resolveMilestoneDurations(milestones, {
    nowMs: now,
    endedAtMs,
    startedAtMs,
  }).slice(-6);

  return (
    <section className={`panel loading-shell loading-phase-${phase}`}>
      <div className="loading-ambient-glow" aria-hidden="true" />
      <div className="split-layout">
        <div className="step-main athlete-motion-slot athlete-motion-main">
          <article className="status-card loading-primary-panel">
            <div className="loading-stage-header">
              <div className="loading-stage-copy">
                <p className="loading-eyebrow">{phaseContent.eyebrow}</p>
                <h1 className="loading-title">
                  {failure ? failure.headline : phaseContent.title}
                  {!isTerminalNonProgress ? (
                    <span className="loading-title-dots" aria-hidden="true">
                      <span />
                      <span />
                      <span />
                    </span>
                  ) : null}
                </h1>
              </div>
              <span className={`loading-phase-badge${isFailed ? " loading-phase-badge-error" : ""}`}>
                {phaseContent.chip}
              </span>
            </div>
            <p className="muted loading-copy">{failure ? failure.detail : phaseContent.copy}</p>
            <GenerationProgressMilestones phase={phase} startedAtMs={startedAtMs} nowMs={now} milestones={milestones} />
            {stageOnePreview ? <StageOnePreviewCard preview={stageOnePreview} /> : null}
            <div className="loading-operational-strip" aria-label={appText("text_6bb9e95b3556")}>
              <div className="loading-operational-item">
                <span className="loading-operational-label">{appText("text_38af1f7f0a63")}</span>
                <span className="loading-operational-value">{phaseContent.chip}</span>
              </div>
              <div className="loading-operational-item">
                <span className="loading-operational-label">{appText("text_bdd254b65baa")}</span>
                <span className="loading-operational-value">{phaseContent.buildState}</span>
              </div>
              <div className="loading-operational-item">
                <span className="loading-operational-label">{isElapsedRunning ? appText("text_a194a68a45d3") : appText("text_f448bdef375a")}</span>
                <span className="loading-operational-value loading-operational-value-mono" aria-live="polite">
                  {elapsedLabel ?? "--"}
                </span>
              </div>
            </div>
            {!isTerminalNonProgress ? (
              <p className="loading-estimate muted">{ESTIMATE_COPY}</p>
            ) : null}
            {showMilestones ? (
              <div className="loading-milestone-feed" aria-label={appText("text_c5416b4c96b4")} aria-live="polite">
                <p className="loading-eyebrow loading-milestone-eyebrow">
                  {isFailed ? appText("text_2ccb67bc406b") : appText("text_4cfdf163329b")}
                </p>
                <ol className="loading-milestone-list">
                  {milestoneDurations.map((view, index) => {
                    const { milestone } = view;
                    // The marker follows the newest row in the feed, which is
                    // not the same question as which stage is still running —
                    // a finished build has a newest row and no running one.
                    const isLatest = index === milestoneDurations.length - 1;
                    const durationLabel = formatMilestoneDurationLabel(view);
                    return (
                      <li
                        key={`${milestone.code}-${milestone.at || index}`}
                        className={`loading-milestone-row${isLatest ? " loading-milestone-row-latest" : ""}`}
                      >
                        <span className="loading-milestone-marker" aria-hidden="true" />
                        <div className="loading-milestone-copy">
                          <span className="loading-milestone-label">{milestone.label || milestone.code}</span>
                          {milestone.detail ? (
                            <span className="loading-milestone-detail">{milestone.detail}</span>
                          ) : null}
                        </div>
                        {durationLabel ? (
                          <span
                            className={`loading-milestone-time${view.isRunning ? " loading-milestone-time-running" : ""}`}
                            title={view.offsetLabel ? `Started ${view.offsetLabel} into the build` : undefined}
                          >
                            {durationLabel}
                          </span>
                        ) : null}
                      </li>
                    );
                  })}
                </ol>
              </div>
            ) : null}
            {!isTerminalNonProgress ? (
              <div className="loading-scan-rail" aria-hidden="true">
                <span className="loading-scan-line" />
              </div>
            ) : null}
            {isFailed ? null : error ? (
              <div className="error-banner">{error}</div>
            ) : (
              <div className="loading-status-strip">{statusMessage ?? phaseContent.statusFallback}</div>
            )}
            {failure ? (
              <div className="loading-failure-actions">
                <p className="loading-failure-headline">{appText("text_05c7efd0a4c9")}</p>
                {/*
                  Every action here changes something. A failed build is
                  terminal, so there is deliberately no "refresh status" —
                  re-reading a finished job cannot revive it, and showing a
                  live-looking status control on a dead build is what made the
                  screen read as if it were generating again.
                */}
                <div className="loading-failure-secondary-actions">
                  {failureActions.map((action) => (
                    <button
                      key={action}
                      type="button"
                      className={action === failure.primary ? "cta" : "cta ghost"}
                      onClick={failureHandlers[action] ?? undefined}
                    >
                      {GENERATION_FAILURE_ACTION_LABELS[action]}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
            {phase === "already_generated" ? (
              <div className="loading-failure-actions">
                <p className="loading-failure-headline">{appText("text_8e03db08cd8b")}</p>
                <div className="loading-failure-secondary-actions">
                  {onOpenPlanHistory ? <button type="button" className="cta ghost" onClick={onOpenPlanHistory}>{appText("text_27faf7ed824c")}</button> : null}
                  {onRefineIntake ? <button type="button" className="cta ghost" onClick={onRefineIntake}>{appText("text_0b028b4d2888")}</button> : null}
                </div>
              </div>
            ) : null}
            {phase === "review_paused" ? (
              <div className="loading-failure-actions">
                <p className="loading-failure-headline">{appText("text_7cccb2da11fd")}</p>
                <div className="loading-failure-secondary-actions">
                  {onReturnToWorkspace ? <button type="button" className="cta" onClick={onReturnToWorkspace}>{appText("text_02e565ef63bc")}</button> : null}
                  {onRefineIntake ? <button type="button" className="cta ghost" onClick={onRefineIntake}>{appText("text_0b028b4d2888")}</button> : null}
                </div>
              </div>
            ) : null}
            <p className="loading-reassurance">{phaseContent.reassurance}</p>
          </article>
        </div>

        <aside className="step-aside athlete-motion-slot athlete-motion-rail">
          {/*
            The progress rail is a live-build instrument: on a stopped build it
            would tick four stages "complete" and blame the last one, which is
            both wrong and reads like work is still happening. A stopped build
            gets a plain account of what it means instead.
          */}
          {isFailed ? (
            <div className="support-panel loading-secondary-panel">
              <div className="form-section-header">
                <p className="loading-eyebrow">{appText("text_067f91a71e1b")}</p>
                <h2 className="form-section-title">{appText("text_483bd49023ae")}</h2>
                <p className="muted">
                  {appText("text_cf35b11d488f")}</p>
              </div>
              <div className="loading-support-note">
                <p className="kicker">{appText("text_834c08cbe8b2")}</p>
                <p className="muted">
                  {appText("text_da7796d1b778")}</p>
              </div>
            </div>
          ) : (
          <div className="support-panel loading-secondary-panel">
            <div className="form-section-header">
              <p className="loading-eyebrow">{appText("text_9d37483e6217")}</p>
              <h2 className="form-section-title">{appText("text_bfa53d99e578")}</h2>
              <p className="muted">{appText("text_d4bc1379ba00")}</p>
            </div>
            <ol className="loading-steps" aria-label={appText("text_d5be10f5d2aa")}>
              {WORKFLOW_STEPS.map((step, index) => {
                const stepState =
                  index < activeIndex
                    ? "complete"
                    : index === activeIndex
                      ? "current"
                      : "upcoming";

                return (
                  <li
                    key={step.key}
                    className={`loading-step loading-step-${stepState}`}
                    aria-current={stepState === "current" ? "step" : undefined}
                  >
                    <span className="loading-step-marker" aria-hidden="true">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span className="loading-step-copy">
                      <span className="loading-step-label">{step.title}</span>
                      <span className="loading-step-note">{step.detail}</span>
                    </span>
                  </li>
                );
              })}
            </ol>
            <div className="loading-support-note">
              <p className="kicker">{appText("text_6ce455bec741")}</p>
              <p className="muted">
                {appText("text_3f68e7777cba")}</p>
            </div>
          </div>
          )}
        </aside>
      </div>
    </section>
  );
}
