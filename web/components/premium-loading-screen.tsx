"use client";

import type { GenerationUiPhase } from "@/lib/generation-controller";

const WORKFLOW_STEPS = [
  {
    key: "submitting",
    title: "Request lock",
    detail: "Save the intake and open a durable background job.",
  },
  {
    key: "queued",
    title: "Queue and runner",
    detail: "Hold your place while the generation runner picks up the job.",
  },
  {
    key: "running",
    title: "Background build",
    detail: "Stage 1 and Stage 2 process the saved request in the background.",
  },
  {
    key: "reconnecting",
    title: "Link recovery",
    detail: "Reconnect to the same saved job if the browser or network drops.",
  },
  {
    key: "finalizing",
    title: "Workspace handoff",
    detail: "Open the saved plan after the final checks close out.",
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
    runnerState: string;
  }
> = {
  submitting: {
    eyebrow: "Generation request",
    title: "Locking in your plan request.",
    copy: "We are saving this intake first, then creating the background job that will carry the full generation safely.",
    chip: "Submitting",
    statusFallback: "Saving your intake and creating the background job now.",
    reassurance: "Safe to leave and return. This workspace reconnects to the same saved job instead of starting over.",
    runnerState: "Dispatching",
  },
  queued: {
    eyebrow: "Mission control",
    title: "Request saved. Runner is queued.",
    copy: "Your plan request is already parked safely in the workspace. The next step is runner pickup, not another submission.",
    chip: "Queued",
    statusFallback: "Your saved job is queued and waiting for the runner.",
    reassurance: "Safe to leave and return. This workspace reconnects to the same saved job instead of starting over.",
    runnerState: "Queued",
  },
  running: {
    eyebrow: "Mission control",
    title: "Generation is live in the background.",
    copy: "Stage 1 and Stage 2 are processing the saved athlete request now while this page watches for the finished handoff.",
    chip: "Running",
    statusFallback: "Your saved job is processing in the background.",
    reassurance: "Safe to leave and return. This workspace reconnects to the same saved job instead of starting over.",
    runnerState: "Active",
  },
  reconnecting: {
    eyebrow: "Connection watch",
    title: "Reconnecting to the same saved job.",
    copy: "The job itself stays intact. We are only restoring the browser link so this page can resume watching the existing request.",
    chip: "Reconnecting",
    statusFallback: "Reconnecting to the saved generation request now.",
    reassurance: "Safe to leave and return. This workspace reconnects to the same saved job instead of starting over.",
    runnerState: "Recovery watch",
  },
  finalizing: {
    eyebrow: "Closing handoff",
    title: "Final checks passed. Opening workspace.",
    copy: "The generation is complete. We are closing the last handoff step before the saved plan opens inside your workspace.",
    chip: "Finalizing",
    statusFallback: "Final checks passed. Opening your saved plan.",
    reassurance: "The saved plan is ready. This page is only closing the final handoff before your workspace opens.",
    runnerState: "Handoff",
  },
  failed: {
    eyebrow: "Generation halted",
    title: "The request stopped before handoff.",
    copy: "The saved request did not reach an openable plan state. Review the error, then retry from the athlete workspace when you are ready.",
    chip: "Needs retry",
    statusFallback: "Generation stopped before the saved plan could open.",
    reassurance: "The saved request needs a retry from the workspace. Review the error first so you do not repeat the same failure.",
    runnerState: "Stopped",
  },
};

interface PremiumLoadingScreenProps {
  phase: GenerationUiPhase;
  error?: string | null;
  statusMessage?: string | null;
}

export function PremiumLoadingScreen({
  phase,
  error = null,
  statusMessage = null,
}: PremiumLoadingScreenProps) {
  const phaseContent = PHASE_CONTENT[phase];
  const activeIndex = PHASE_ORDER[phase];

  return (
    <section className={`panel loading-shell loading-phase-${phase}`}>
      <div className="split-layout">
        <div className="step-main athlete-motion-slot athlete-motion-main">
          <article className="status-card loading-primary-panel">
            <div className="loading-stage-header">
              <div className="loading-stage-copy">
                <p className="loading-eyebrow">{phaseContent.eyebrow}</p>
                <h1 className="loading-title">{phaseContent.title}</h1>
              </div>
              <span className={`loading-phase-badge${phase === "failed" ? " loading-phase-badge-error" : ""}`}>
                {phaseContent.chip}
              </span>
            </div>
            <p className="muted loading-copy">{phaseContent.copy}</p>
            <div className="loading-operational-strip" aria-label="Generation status">
              <div className="loading-operational-item">
                <span className="loading-operational-label">Job state</span>
                <span className="loading-operational-value">{phaseContent.chip}</span>
              </div>
              <div className="loading-operational-item">
                <span className="loading-operational-label">Runner</span>
                <span className="loading-operational-value">{phaseContent.runnerState}</span>
              </div>
              <div className="loading-operational-item">
                <span className="loading-operational-label">Persistence</span>
                <span className="loading-operational-value">Saved immediately</span>
              </div>
            </div>
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
            <p className="loading-reassurance">{phaseContent.reassurance}</p>
          </article>
        </div>

        <aside className="step-aside athlete-motion-slot athlete-motion-rail">
          <div className="support-panel loading-secondary-panel">
            <div className="form-section-header">
              <p className="loading-eyebrow">Workflow rail</p>
              <h2 className="form-section-title">Mission control</h2>
              <p className="muted">The highlighted stage follows the real saved job state, not a fake timer.</p>
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
                If the browser closes or the network drops, the next visit reconnects to the same saved request.
              </p>
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
}
