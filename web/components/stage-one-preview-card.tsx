"use client";

import type { StageOnePreview } from "@/lib/stage-one-preview";

interface StageOnePreviewCardProps {
  preview: StageOnePreview | null;
}

function formatList(values: string[], max = 3): string {
  if (values.length === 0) return "";
  if (values.length <= max) return values.join(", ");
  const visible = values.slice(0, max).join(", ");
  return `${visible} +${values.length - max} more`;
}

function formatPhaseSplit(phases: StageOnePreview["camp"]["phaseWeeks"]): string {
  const parts: string[] = [];
  if (phases.GPP > 0) parts.push(`${phases.GPP}w GPP`);
  if (phases.SPP > 0) parts.push(`${phases.SPP}w SPP`);
  if (phases.TAPER > 0) parts.push(`${phases.TAPER}w taper`);
  return parts.join(" · ") || "Single block";
}

function formatCamp(camp: StageOnePreview["camp"]): string {
  const weeks = camp.campWeeks > 0 ? `${camp.campWeeks}-week camp` : "Camp shape ready";
  const window = camp.isOpenCamp ? "Open camp" : camp.fightDate ? `Fight ${camp.fightDate}` : "";
  return window ? `${weeks} · ${window}` : weeks;
}

function formatFocus(focus: StageOnePreview["focus"]): string {
  const goal = focus.primaryGoal || focus.keyGoals[0] || "";
  const weak = focus.primaryWeakArea || focus.weakAreas[0] || "";
  if (goal && weak) return `${goal} → close ${weak}`;
  if (goal) return goal;
  if (weak) return `Close ${weak}`;
  return "Balanced camp focus";
}

function formatSchedule(schedule: StageOnePreview["schedule"]): string {
  const parts: string[] = [];
  if (schedule.weeklyTrainingFrequency) {
    parts.push(`${schedule.weeklyTrainingFrequency}/wk`);
  }
  if (schedule.availableDays > 0) {
    parts.push(`${schedule.availableDays} available days`);
  }
  if (schedule.roundsFormat) {
    parts.push(schedule.roundsFormat);
  }
  return parts.join(" · ") || "Schedule from intake";
}

function formatRestrictions(restrictions: StageOnePreview["restrictions"]): string {
  const equipment = restrictions.equipmentAccess.length
    ? `Equipment: ${formatList(restrictions.equipmentAccess)}`
    : "Equipment: full gym assumed";
  const injuryCount = restrictions.parsedInjuryCount;
  const injurySummary = injuryCount > 0
    ? `${injuryCount} injury note${injuryCount === 1 ? "" : "s"} accounted for`
    : restrictions.injuriesText
      ? "Injury notes captured"
      : "No injuries reported";
  return `${equipment} · ${injurySummary}`;
}

function formatSafety(notes: StageOnePreview["safetyNotes"]): string {
  if (notes.length === 0) {
    return "No exceptional safety flags — standard camp routing.";
  }
  return notes.map((note) => note.message).join(" ");
}

export function StageOnePreviewCard({ preview }: StageOnePreviewCardProps) {
  if (!preview) return null;

  const rows: { label: string; value: string }[] = [
    { label: "Camp", value: formatCamp(preview.camp) },
    { label: "Phases", value: formatPhaseSplit(preview.camp.phaseWeeks) },
    { label: "Focus", value: formatFocus(preview.focus) },
    { label: "Schedule", value: formatSchedule(preview.schedule) },
    { label: "Restrictions", value: formatRestrictions(preview.restrictions) },
    { label: "Safety notes", value: formatSafety(preview.safetyNotes) },
  ];

  return (
    <section className="loading-stage1-preview" aria-label="Draft structure preview">
      <header className="loading-stage1-preview-header">
        <p className="loading-eyebrow loading-stage1-preview-eyebrow">Draft structure ready</p>
        <h3 className="loading-stage1-preview-title">Camp shape locked in</h3>
        <p className="loading-stage1-preview-copy">
          We&rsquo;ve built the camp structure from your intake. The final coach review is still running, so details
          may change before completion.
        </p>
      </header>
      <dl className="loading-stage1-preview-rows">
        {rows.map((row) => (
          <div key={row.label} className="loading-stage1-preview-row">
            <dt className="loading-stage1-preview-row-label">{row.label}</dt>
            <dd className="loading-stage1-preview-row-value">{row.value}</dd>
          </div>
        ))}
      </dl>
      <p className="loading-stage1-preview-chip" aria-live="polite">
        Preview &mdash; final plan still generating
      </p>
    </section>
  );
}
