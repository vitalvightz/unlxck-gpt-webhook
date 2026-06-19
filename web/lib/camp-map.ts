// Pure, defensive helpers that turn a structured_plan into the "camp map" view:
// where the athlete is in the camp (current week/day), per-week/day completion,
// a load proxy derived from day types, and the compact readiness strip. Kept
// framework-free and node:test-able, mirroring lib/structured-plan.ts. Every
// function tolerates null/partial payloads and never throws.
import { formatPlanLabel } from "./plan-labels.ts";
import {
  cleanText,
  getDays,
  getDisplayableRedFlags,
  getPlanNotes,
  getSessions,
  getWeeks,
  redFlagView,
} from "./structured-plan.ts";
import type {
  StructuredDay,
  StructuredPlan,
  StructuredWeek,
} from "@/lib/types";

/** Local-calendar ISO date (YYYY-MM-DD) for a Date, matching day.date strings. */
export function toISODate(date: Date): string {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/** The plain date portion of a possibly-datetime day.date string, or null. */
function dayISO(day: StructuredDay | null | undefined): string | null {
  const raw = cleanText(day?.date);
  if (!raw) {
    return null;
  }
  // Day dates are plain "YYYY-MM-DD" but tolerate an ISO datetime suffix.
  return raw.slice(0, 10);
}

export type PlanProgress = {
  weekCount: number;
  /** Array index of the week containing today, or null when out of camp range. */
  currentWeekPos: number | null;
  /** ISO date of today's day inside the plan, or null when out of range. */
  currentDayDate: string | null;
  /** "D-28" style countdown for today (from the day, else derived), or null. */
  dLabel: string | null;
};

/**
 * Resolve where the athlete is in the camp relative to `today`. Matches today to
 * a day by calendar date; when today falls outside every scheduled day the
 * current markers are null (callers default selection to the first week) and the
 * countdown label is derived from the event date when available.
 */
export function resolvePlanProgress(
  plan: StructuredPlan | null | undefined,
  today: Date,
): PlanProgress {
  const weeks = getWeeks(plan);
  const todayIso = toISODate(today);
  let currentWeekPos: number | null = null;
  let currentDayDate: string | null = null;

  weeks.forEach((week, weekPos) => {
    if (getDays(week).some((day) => dayISO(day) === todayIso)) {
      currentWeekPos = weekPos;
      currentDayDate = todayIso;
    }
  });

  const currentDay = findDayByISO(plan, currentDayDate);
  const dLabel = cleanText(currentDay?.countdown_label) || deriveCountdownLabel(plan, today);

  return { weekCount: weeks.length, currentWeekPos, currentDayDate, dLabel };
}

/** "D-28" derived from the event date minus today, or null when unavailable. */
export function deriveCountdownLabel(
  plan: StructuredPlan | null | undefined,
  today: Date,
): string | null {
  const eventIso =
    cleanText(plan?.event_context?.fight_date) || cleanText(plan?.event_context?.match_date);
  if (!eventIso) {
    return null;
  }
  const event = new Date(`${eventIso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(event.getTime())) {
    return null;
  }
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const msPerDay = 24 * 60 * 60 * 1000;
  const diffDays = Math.round((event.getTime() - startOfToday.getTime()) / msPerDay);
  if (diffDays < 0) {
    return null;
  }
  return diffDays === 0 ? "D0" : `D-${diffDays}`;
}

export type Completion = { done: number; total: number };

/** Sessions marked done over total sessions across all of a week's days. */
export function weekCompletion(week: StructuredWeek | null | undefined): Completion {
  return getDays(week).reduce<Completion>(
    (acc, day) => {
      const dayDone = dayCompletion(day);
      return { done: acc.done + dayDone.done, total: acc.total + dayDone.total };
    },
    { done: 0, total: 0 },
  );
}

/** Sessions marked done over total sessions for a single day. */
export function dayCompletion(day: StructuredDay | null | undefined): Completion {
  const sessions = getSessions(day);
  const done = sessions.filter(
    (session) => cleanText(session.completion_status)?.toLowerCase() === "done",
  ).length;
  return { done, total: sessions.length };
}

const LOAD_PRIORITY = ["high", "moderate", "low", "recovery", "rest", "off"];

/**
 * A short load label for a week, derived from its days' `day_type` values (the
 * payload carries no explicit week load focus). Returns the most demanding
 * non-empty day type present, titleized, or null when no day types exist.
 */
export function weekLoadProxy(week: StructuredWeek | null | undefined): string | null {
  const types = getDays(week)
    .map((day) => cleanText(day.day_type)?.toLowerCase())
    .filter((type): type is string => Boolean(type));
  if (types.length === 0) {
    return null;
  }
  for (const candidate of LOAD_PRIORITY) {
    if (types.includes(candidate)) {
      return formatPlanLabel(candidate);
    }
  }
  return formatPlanLabel(types[0]);
}

/** Find the day in a plan matching an ISO date, or null. */
export function findDayByISO(
  plan: StructuredPlan | null | undefined,
  iso: string | null,
): StructuredDay | null {
  if (!iso) {
    return null;
  }
  for (const week of getWeeks(plan)) {
    for (const day of getDays(week)) {
      if (dayISO(day) === iso) {
        return day;
      }
    }
  }
  return null;
}

export type ReadinessStrip = {
  todayCall: string | null;
  focus: string | null;
  risk: string | null;
  load: string | null;
};

/**
 * The compact readiness/risk strip. Today's call comes from the current day's
 * today_card; focus prefers the current/selected week goal; risk is the top
 * displayable red flag (else an injury active-note); load is the current day's
 * type. Everything is nullable so callers render only the cards with data — no
 * invented HRV/recovery scores.
 */
export function getReadinessStrip(
  plan: StructuredPlan | null | undefined,
  currentDay: StructuredDay | null | undefined,
  focusWeek: StructuredWeek | null | undefined,
): ReadinessStrip {
  const card = currentDay?.today_card;
  const todayCall = cleanText(card?.headline) || formatReadinessStatus(card?.readiness_status);

  let focus = cleanText(focusWeek?.week_goal);
  if (!focus) {
    const firstSession = getSessions(currentDay)[0];
    focus = cleanText(firstSession?.title) || cleanText(firstSession?.objective);
  }

  const topFlag = getDisplayableRedFlags(plan)[0];
  let risk = topFlag ? redFlagView(topFlag).text : null;
  if (!risk) {
    const injuryNote = getPlanNotes(plan).find((note) => note.category === "injury");
    risk = injuryNote?.text ?? null;
  }

  const load = formatPlanLabel(cleanText(currentDay?.day_type) ?? "") || null;

  return { todayCall, focus, risk, load };
}

/** Titleize a readiness_status enum ("train_as_planned" -> "Train as planned"). */
function formatReadinessStatus(value: unknown): string | null {
  const clean = cleanText(value);
  return clean ? formatPlanLabel(clean) : null;
}
