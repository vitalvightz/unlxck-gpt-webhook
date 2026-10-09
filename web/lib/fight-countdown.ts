// Fight-camp countdown: days to fight night, how far through camp the athlete
// is, and the next phase change. The fight date and training day come from the
// server (/api/today: active_plan.fight_date, today.training_day) — the same
// values the Overview "Camp day" field uses — so the countdown can't disagree
// with the rest of the page. The structured plan only supplies the week
// calendar (start/end dates and phase per week). Open plans with no fight date
// get no countdown. Pure and defensive: never throws.
import { humanizeIfRawEnum } from "./plan-labels.ts";
import type { StructuredPlan } from "@/lib/types";

export type FightCountdown = {
  /** Whole days until fight night; 0 on fight day. */
  daysOut: number;
  fightDateISO: string;
  /** 0-100 position between camp start and fight night, or null without a
   * usable week calendar. */
  pct: number | null;
  /** "Week 2 of 8", or null when today sits outside the plan's weeks. */
  weekLabel: string | null;
  /** Athlete-facing current phase ("General prep"), or null. */
  phaseLabel: string | null;
  /** "Specific prep starts in 10 days" / "Fight night tomorrow", or null on fight day. */
  nextLabel: string | null;
};

const MS_PER_DAY = 86_400_000;

/** UTC-noon ms for the date part of an ISO string, so day differences are DST-safe. */
function isoDayMs(value: string | null | undefined): number | null {
  const iso = typeof value === "string" ? value.trim().slice(0, 10) : "";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    return null;
  }
  const ms = new Date(`${iso}T12:00:00Z`).getTime();
  return Number.isNaN(ms) ? null : ms;
}

function inDays(days: number): string {
  return days === 1 ? "tomorrow" : `in ${days} days`;
}

export function getFightCountdown(input: {
  fightDate: string | null | undefined;
  trainingDay: string | null | undefined;
  phase?: string | null;
  plan?: StructuredPlan | null;
}): FightCountdown | null {
  const fightMs = isoDayMs(input.fightDate);
  const todayMs = isoDayMs(input.trainingDay);
  if (fightMs === null || todayMs === null) {
    return null;
  }
  const daysOut = Math.round((fightMs - todayMs) / MS_PER_DAY);
  if (daysOut < 0) {
    return null;
  }

  const weeks = (Array.isArray(input.plan?.weeks) ? input.plan.weeks : [])
    .map((week) => ({
      startMs: isoDayMs(week?.start_date),
      endMs: isoDayMs(week?.end_date),
      phase: typeof week?.phase_label === "string" ? week.phase_label.trim() : "",
    }))
    .filter((week): week is { startMs: number; endMs: number; phase: string } =>
      week.startMs !== null && week.endMs !== null,
    )
    .sort((a, b) => a.startMs - b.startMs);

  const campStartMs = weeks.length ? weeks[0].startMs : null;
  const pct =
    campStartMs !== null && fightMs > campStartMs
      ? Math.max(0, Math.min(100, ((todayMs - campStartMs) / (fightMs - campStartMs)) * 100))
      : null;

  const currentIndex = weeks.findIndex((week) => todayMs >= week.startMs && todayMs <= week.endMs);
  const currentWeek = currentIndex >= 0 ? weeks[currentIndex] : null;
  const weekLabel = currentWeek ? `Week ${currentIndex + 1} of ${weeks.length}` : null;
  const phaseLabel = humanizeIfRawEnum(input.phase?.trim() || currentWeek?.phase || "") || null;

  let nextLabel: string | null = null;
  if (daysOut > 0) {
    const nextPhase = currentWeek
      ? weeks.slice(currentIndex + 1).find((week) => week.phase && week.phase !== currentWeek.phase)
      : null;
    const nextPhaseDays = nextPhase ? Math.round((nextPhase.startMs - todayMs) / MS_PER_DAY) : null;
    nextLabel =
      nextPhase && nextPhaseDays !== null && nextPhaseDays > 0 && nextPhaseDays < daysOut
        ? `${humanizeIfRawEnum(nextPhase.phase)} starts ${inDays(nextPhaseDays)}`
        : `Fight night ${inDays(daysOut)}`;
  }

  return {
    daysOut,
    fightDateISO: new Date(fightMs).toISOString().slice(0, 10),
    pct,
    weekLabel,
    phaseLabel,
    nextLabel,
  };
}
