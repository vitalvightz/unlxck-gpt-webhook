// Fight-camp countdown: days to fight night, how far through camp the athlete
// is, and the next phase change. The fight date and training day come from the
// server (/api/today: active_plan.fight_date, today.training_day) — the same
// values the Overview "Camp day" field uses — so the countdown can't disagree
// with the rest of the page. The structured plan only supplies the calendar:
// weeks come from getWeeks() (which splits long late-fight blocks into Mon-Sun
// weeks, matching the plan page) and phases are read per day, since a phase
// can change mid-week. Open plans with no fight date get no countdown. Pure and
// defensive: never throws.
import { humanizeIfRawEnum } from "./plan-labels.ts";
import { cleanText, getDays, getWeeks, resolvedWeekPhase } from "./structured-plan.ts";
import type { StructuredPlan } from "@/lib/types";

export type FightCountdown = {
  /** Whole days until fight night; 0 on fight day. */
  daysOut: number;
  fightDateISO: string;
  /** Whole days from camp start to fight night, or null without a usable
   * calendar. Used as the countdown animation's starting number. */
  campDays: number | null;
  /** 0-100 position between camp start and fight night, or null without a
   * usable calendar. */
  pct: number | null;
  /** "Week 2 of 8", or null when today sits outside the plan's weeks. */
  weekLabel: string | null;
  /** Athlete-facing current phase ("General prep"), or null. */
  phaseLabel: string | null;
  /** "Specific prep starts in 10 days" / "Fight night tomorrow", or null on fight day. */
  nextLabel: string | null;
};

const MS_PER_DAY = 86_400_000;

/** UTC-noon ms for a real calendar date ("YYYY-MM-DD", optionally with a time
 * suffix), so day differences are DST-safe. Impossible dates such as
 * 2026-02-31 are rejected rather than rolled into the next month. */
function isoDayMs(value: string | null | undefined): number | null {
  const iso = typeof value === "string" ? value.trim().slice(0, 10) : "";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    return null;
  }
  const date = new Date(`${iso}T12:00:00Z`);
  if (Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== iso) {
    return null;
  }
  return date.getTime();
}

function phaseKey(value: unknown): string | null {
  return cleanText(value)?.toUpperCase() ?? null;
}

function inDays(days: number): string {
  return days === 1 ? "tomorrow" : `in ${days} days`;
}

type CalendarDay = { ms: number; phase: string | null; weekIndex: number };
type CalendarWeek = { startMs: number | null; endMs: number | null; phase: string | null };

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

  // Calendar from the same week list the plan page renders.
  const weeks: CalendarWeek[] = [];
  const days: CalendarDay[] = [];
  getWeeks(input.plan).forEach((week, weekIndex) => {
    const weekPhase = phaseKey(resolvedWeekPhase(week));
    weeks.push({ startMs: isoDayMs(week.start_date), endMs: isoDayMs(week.end_date), phase: weekPhase });
    getDays(week).forEach((day) => {
      const ms = isoDayMs(day.date);
      if (ms !== null) {
        days.push({ ms, phase: phaseKey(day.phase_label) ?? weekPhase, weekIndex });
      }
    });
  });
  days.sort((a, b) => a.ms - b.ms);

  const startCandidates = [
    ...weeks.map((week) => week.startMs).filter((ms): ms is number => ms !== null),
    ...days.map((day) => day.ms),
  ];
  const campStartMs = startCandidates.length ? Math.min(...startCandidates) : null;
  const hasCalendar = campStartMs !== null && fightMs > campStartMs;
  const pct = hasCalendar
    ? Math.max(0, Math.min(100, ((todayMs - campStartMs) / (fightMs - campStartMs)) * 100))
    : null;
  const campDays = hasCalendar ? Math.round((fightMs - campStartMs) / MS_PER_DAY) : null;

  // Today's week: the week holding today's dated day, else the week whose
  // date range covers today.
  const todayDay = days.find((day) => day.ms === todayMs) ?? null;
  const weekIndex =
    todayDay?.weekIndex ??
    weeks.findIndex((week) => week.startMs !== null && week.endMs !== null && todayMs >= week.startMs && todayMs <= week.endMs);
  const currentWeek = weekIndex >= 0 ? weeks[weekIndex] : null;
  const weekLabel = currentWeek ? `Week ${weekIndex + 1} of ${weeks.length}` : null;

  // Today's phase for spotting the next change: the day's own phase, else its
  // week's. The displayed label prefers the server's active-plan phase.
  const todayPhase = todayDay?.phase ?? currentWeek?.phase ?? null;
  const phaseLabel = humanizeIfRawEnum(cleanText(input.phase) ?? todayPhase ?? "") || null;

  let nextLabel: string | null = null;
  if (daysOut > 0) {
    // First dated day after today, before fight night, in a different phase.
    const nextChange = todayPhase
      ? days.find((day) => day.ms > todayMs && day.ms < fightMs && day.phase && day.phase !== todayPhase)
      : undefined;
    nextLabel = nextChange?.phase
      ? `${humanizeIfRawEnum(nextChange.phase)} starts ${inDays(Math.round((nextChange.ms - todayMs) / MS_PER_DAY))}`
      : `Fight night ${inDays(daysOut)}`;
  }

  return {
    daysOut,
    campDays,
    fightDateISO: new Date(fightMs).toISOString().slice(0, 10),
    pct,
    weekLabel,
    phaseLabel,
    nextLabel,
  };
}
