"use client";

import { useEffect, useState } from "react";

import { GenerationProgressMilestones } from "@/components/generation-progress-milestones";
import { StageOnePreviewCard } from "@/components/stage-one-preview-card";
import type { GenerationUiPhase } from "@/lib/generation-controller";
import { buildStageOnePreview } from "@/lib/stage-one-preview";
import type { PlanRequest, ProgressMilestone } from "@/lib/types";

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
  failed: 4,
};

const PHASE_CONTENT: Record<
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
  failed: {
    eyebrow: "Generation stopped",
    title: "Plan failed. Try again.",
    copy: "The saved intake did not reach an openable plan state. You can retry from the athlete workspace.",
    chip: "Needs retry",
    statusFallback: "Plan failed. Try again.",
    reassurance: "Your intake is still saved. Return to the workspace when you are ready to retry.",
    buildState: "Stopped",
  },
};

function formatElapsed(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes === 0) {
    return `${seconds}s`;
  }
  return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
}

const ESTIMATE_COPY = "Plan build has started. You can leave and return later; the saved build keeps running.";

interface PremiumLoadingScreenProps {
  phase: GenerationUiPhase;
  error?: string | null;
  statusMessage?: string | null;
  startedAtMs?: number | null;
  milestones?: ProgressMilestone[];
  intake?: PlanRequest | null;
  onRetry?: (() => void) | null;
  canRetry?: boolean;
  onOpenPlanHistory?: (() => void) | null;
  onReturnToWorkspace?: (() => void) | null;
  onRefreshStatus?: (() => void) | null;
}

function formatRelativeTimestamp(at: string, baseMs: number | null): string {
  const eventMs = Date.parse(at || "");
  if (!Number.isFinite(eventMs)) {
    return "";
  }
  if (baseMs === null) {
    return "";
  }
  const diffSeconds = Math.max(0, Math.floor((eventMs - baseMs) / 1000));
  if (diffSeconds < 60) {
    return `+${diffSeconds}s`;
  }
  const minutes = Math.floor(diffSeconds / 60);
  const seconds = diffSeconds % 60;
  return `+${minutes}m ${String(seconds).padStart(2, "0")}s`;
}

export function PremiumLoadingScreen({
  phase,
  error = null,
  statusMessage = null,
  startedAtMs = null,
  milestones = [],
  intake = null,
  onRetry = null,
  canRetry = false,
  onOpenPlanHistory = null,
  onReturnToWorkspace = null,
  onRefreshStatus = null,
}: PremiumLoadingScreenProps) {
  const phaseContent = PHASE_CONTENT[phase];
  const activeIndex = PHASE_ORDER[phase];
  const showElapsed = phase !== "failed" && phase !== "finalizing" && startedAtMs !== null;
  const [now, setNow] = useState(() => Date.now());
  const stageOnePreview = phase === "failed" ? null : buildStageOnePreview(intake, milestones);

  useEffect(() => {
    if (!showElapsed) {
      return;
    }
    setNow(Date.now());
    const interval = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [showElapsed]);

  const elapsedLabel = showElapsed && startedAtMs !== null ? formatElapsed(now - startedAtMs) : null;
  const showMilestones = phase !== "submitting" && milestones.length > 0;
  const visibleMilestones = milestones.slice(-6);
  const latestMilestone = milestones.length ? milestones[milestones.length - 1] : null;

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
                  {phaseContent.title}
                  {phase !== "failed" ? (
                    <span className="loading-title-dots" aria-hidden="true">
                      <span />
                      <span />
                      <span />
                    </span>
                  ) : null}
                </h1>
              </div>
              <span className={`loading-phase-badge${phase === "failed" ? " loading-phase-badge-error" : ""}`}>
                {phaseContent.chip}
              </span>
            </div>
            <p className="muted loading-copy">{phaseContent.copy}</p>
            <GenerationProgressMilestones phase={phase} startedAtMs={startedAtMs} nowMs={now} milestones={milestones} />
            {stageOnePreview ? <StageOnePreviewCard preview={stageOnePreview} /> : null}
            <div className="loading-operational-strip" aria-label="Generation status">
              <div className="loading-operational-item">
                <span className="loading-operational-label">Job state</span>
                <span className="loading-operational-value">{phaseContent.chip}</span>
              </div>
              <div className="loading-operational-item">
                <span className="loading-operational-label">Build</span>
                <span className="loading-operational-value">{phaseContent.buildState}</span>
              </div>
              <div className="loading-operational-item">
                <span className="loading-operational-label">Elapsed</span>
                <span className="loading-operational-value loading-operational-value-mono" aria-live="polite">
                  {elapsedLabel ?? "--"}
                </span>
              </div>
            </div>
            {phase !== "failed" ? (
              <p className="loading-estimate muted">{ESTIMATE_COPY}</p>
            ) : null}
            {showMilestones ? (
              <div className="loading-milestone-feed" aria-label="Generation milestones" aria-live="polite">
                <p className="loading-eyebrow loading-milestone-eyebrow">Plan activity</p>
                <ol className="loading-milestone-list">
                  {visibleMilestones.map((milestone, index) => {
                    const isLatest = milestone === latestMilestone;
                    const relativeLabel = formatRelativeTimestamp(milestone.at, startedAtMs);
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
                        {relativeLabel ? (
                          <span className="loading-milestone-time">{relativeLabel}</span>
                        ) : null}
                      </li>
                    );
                  })}
                </ol>
              </div>
            ) : null}
            {phase !== "failed" ? (
              <div className="loading-scan-rail" aria-hidden="true">
                <span className="loading-scan-line" />
              </div>
            ) : null}
            {error ? (
              <div className="error-banner">{error}</div>
            ) : (
              <div className="loading-status-strip">{statusMessage ?? phaseContent.statusFallback}</div>
            )}
            {phase === "failed" ? (
              <div className="loading-failure-actions">
                <p className="loading-failure-headline">Generation failed.</p>
                {onRetry && canRetry ? (
                  <button
                    type="button"
                    className="cta"
                    onClick={onRetry}
                  >
                    Try again
                  </button>
                ) : null}
                {!canRetry ? (
                  <div className="loading-failure-secondary-actions">
                    {onOpenPlanHistory ? <button type="button" className="cta ghost" onClick={onOpenPlanHistory}>Open plan history</button> : null}
                    {onReturnToWorkspace ? <button type="button" className="cta ghost" onClick={onReturnToWorkspace}>Return to workspace</button> : null}
                    {onRefreshStatus ? <button type="button" className="cta ghost" onClick={onRefreshStatus}>Refresh status</button> : null}
                  </div>
                ) : null}
              </div>
            ) : null}
            <p className="loading-reassurance">{phaseContent.reassurance}</p>
          </article>
        </div>

        <aside className="step-aside athlete-motion-slot athlete-motion-rail">
          <div className="support-panel loading-secondary-panel">
            <div className="form-section-header">
              <p className="loading-eyebrow">Build steps</p>
              <h2 className="form-section-title">Plan progress</h2>
              <p className="muted">The highlighted stage follows the real saved plan state, not a fake timer.</p>
            </div>
            <ol className="loading-steps" aria-label="Generation workflow">
              {WORKFLOW_STEPS.map((step, index) => {
                const stepState =
                  phase === "failed" && index === activeIndex
                    ? "error"
                    : index < activeIndex
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
              <p className="kicker">Return flow</p>
              <p className="muted">
                If the browser closes or the network drops, the next visit reconnects to the same saved plan build.
              </p>
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
}
