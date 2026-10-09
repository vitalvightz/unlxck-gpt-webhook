"use client";

import { getCampProgress } from "@/lib/camp-map";
import type { StructuredPlan } from "@/lib/types";

/**
 * Glanceable "how far through camp" bar, shared by Today and Overview so the two
 * always agree. Renders nothing until there's enough of a plan to draw a
 * meaningful timeline (see getCampProgress), so callers can drop it in
 * unconditionally. `variant` only shifts spacing to sit inside each surface.
 */
export function CampProgressBar({
  plan,
  trainingDay,
  variant = "today",
}: {
  plan: StructuredPlan | null | undefined;
  trainingDay: Date | null;
  variant?: "today" | "overview";
}) {
  const progress = getCampProgress(plan, trainingDay);
  if (!progress) {
    return null;
  }

  const { pct, weekLabel, dLabel } = progress;
  const rounded = Math.round(pct);
  const meta = [weekLabel, dLabel].filter(Boolean).join(" · ");

  return (
    <div
      className="camp-progress"
      data-variant={variant}
      role="progressbar"
      aria-valuenow={rounded}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`Camp progress${weekLabel ? `, ${weekLabel}` : ""}${dLabel ? `, ${dLabel} to fight` : ""}`}
    >
      <div className="camp-progress-head">
        <span className="camp-progress-label">Camp progress</span>
        <span className="camp-progress-meta">{meta || `${rounded}%`}</span>
      </div>
      <div className="overview-progress-track camp-progress-track" aria-hidden="true">
        <span className="overview-progress-fill camp-progress-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
