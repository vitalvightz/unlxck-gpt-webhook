"use client";

import { useMemo } from "react";

import { GENERATION_MILESTONES, getGenerationMilestoneView } from "@/lib/generation-milestones";
import type { GenerationUiPhase } from "@/lib/generation-controller";

interface GenerationProgressMilestonesProps {
  phase: GenerationUiPhase;
  startedAtMs: number | null;
  nowMs: number;
}

export function GenerationProgressMilestones({ phase, startedAtMs, nowMs }: GenerationProgressMilestonesProps) {
  const view = useMemo(() => getGenerationMilestoneView(phase, startedAtMs, nowMs), [nowMs, phase, startedAtMs]);
  if (phase === "failed") {
    return null;
  }
  const progressPct = Math.max(2, Math.min(100, Math.round(((view.currentIndex + 1) / GENERATION_MILESTONES.length) * 100)));
  const recentCompleted = view.completed.slice(-4).reverse();

  return (
    <div className="loading-milestone-rotator" aria-live="polite" aria-label="Generation milestones">
      <p className="loading-eyebrow loading-milestone-eyebrow">Generation milestones</p>
      <h3 className="loading-milestone-current-title">{view.current.title}</h3>
      <p className="loading-milestone-current-detail">{view.current.detail}</p>
      <div className="loading-milestone-progress" role="progressbar" aria-valuemin={0} aria-valuemax={GENERATION_MILESTONES.length} aria-valuenow={view.currentIndex + 1}>
        <span className="loading-milestone-progress-fill" style={{ width: `${progressPct}%` }} />
      </div>
      {recentCompleted.length > 0 ? (
        <ol className="loading-milestone-recent">
          {recentCompleted.map((milestone, index) => (
            <li key={`${milestone.title}-${index}`}>{milestone.title}</li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
