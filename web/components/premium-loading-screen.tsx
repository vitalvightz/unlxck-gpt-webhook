"use client";

import { useEffect, useState } from "react";

const STEPS = [
  "Load the latest saved onboarding",
  "Run the draft planner and Stage 2 automation",
  "Validate the final structure and readiness",
  "Save the final plan and open control room detail",
];

const STEP_INTERVAL_MS = 2200;

interface PremiumLoadingScreenProps {
  error?: string | null;
  statusMessage?: string | null;
}

export function PremiumLoadingScreen({ error = null, statusMessage = null }: PremiumLoadingScreenProps) {
  const [activeStep, setActiveStep] = useState(0);

  useEffect(() => {
    if (error) return;
    const timer = setInterval(() => {
      setActiveStep((prev) => (prev + 1) % STEPS.length);
    }, STEP_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [error]);

  return (
    <section className="panel loading-shell">
      <div className="split-layout">
        <div className="step-main">
          <article className="status-card loading-primary-panel">
            <p className="loading-eyebrow">GENERATING</p>
            <h1 className="loading-title">BUILDING YOUR PLAN</h1>
            <p className="muted loading-copy">
              Running Stage 1 generation, Stage 2 finalization, and validation from your saved onboarding.
            </p>
            <div className="loading-scan-rail" aria-hidden="true">
              <span className="loading-scan-line" />
            </div>
            {error ? (
              <div className="error-banner">{error}</div>
            ) : (
              <div className="loading-status-strip">
                {statusMessage ?? "Precision checks are running before your final plan opens."}
              </div>
            )}
          </article>
        </div>
        <aside className="step-aside">
          <div className="support-panel loading-secondary-panel">
            <div className="form-section-header">
              <p className="loading-eyebrow">CURRENT ACTION</p>
              <h2 className="form-section-title">Generation flow</h2>
            </div>
            <ol className="loading-steps" aria-label="Generation steps">
              {STEPS.map((step, index) => {
                const isActive = index === activeStep;
                return (
                  <li
                    key={step}
                    className={`loading-step${isActive ? " loading-step-active" : ""}`}
                    aria-current={isActive ? "step" : undefined}
                  >
                    <span className="loading-step-marker" aria-hidden="true" />
                    <span className="loading-step-label">{step}</span>
                  </li>
                );
              })}
            </ol>
          </div>
        </aside>
      </div>
    </section>
  );
}
