"use client";

import { useMemo } from "react";

import { GENERATION_MILESTONES, getGenerationMilestoneView } from "@/lib/generation-milestones";
import type { GenerationUiPhase } from "@/lib/generation-controller";
import type { ProgressMilestone } from "@/lib/types";
import { useTranslations as useAppTranslations } from "next-intl";
import { translateUiText } from "@/i18n/ui-text";


interface GenerationProgressMilestonesProps {
  phase: GenerationUiPhase;
  startedAtMs: number | null;
  nowMs: number;
  milestones?: ProgressMilestone[];
}

export function GenerationProgressMilestones({ phase, startedAtMs, nowMs, milestones = [] }: GenerationProgressMilestonesProps) {
    const appText = useAppTranslations("AppText");
  const view = useMemo(() => getGenerationMilestoneView(phase, startedAtMs, nowMs, milestones), [milestones, nowMs, phase, startedAtMs]);
  if (phase === "failed") {
    return null;
  }
  const progressPct = Math.max(2, Math.min(100, Math.round(((view.currentIndex + 1) / GENERATION_MILESTONES.length) * 100)));
  const recentCompleted = view.completed.slice(-4).reverse();

  return (
    <div className="loading-milestone-rotator" aria-live="polite" aria-label={appText("text_c5416b4c96b4")}>
      <p className="loading-eyebrow loading-milestone-eyebrow">{appText("text_c5416b4c96b4")}</p>
      <h3 className="loading-milestone-current-title">{translateUiText(appText, view.current.title)}</h3>
      <p className="loading-milestone-current-detail">{view.current.detail}</p>
      <div className="loading-milestone-progress" role="progressbar" aria-valuemin={0} aria-valuemax={GENERATION_MILESTONES.length} aria-valuenow={view.currentIndex + 1}>
        <span className="loading-milestone-progress-fill" style={{ width: `${progressPct}%` }} />
      </div>
      {recentCompleted.length > 0 ? (
        <ol className="loading-milestone-recent">
          {recentCompleted.map((milestone, index) => (
            <li key={`${milestone.title}-${index}`}>{translateUiText(appText, milestone.title)}</li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
