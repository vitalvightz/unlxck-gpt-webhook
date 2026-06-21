// Pure, defensive helpers that turn a structured_plan into the "camp map" view:
// where the athlete is in the camp (current week/day), per-week/day completion,
// a load proxy derived from day types, and the compact readiness strip. Kept
// framework-free and node:test-able, mirroring lib/structured-plan.ts. Every
// function tolerates null/partial payloads and never throws.
import { formatPlanLabel } from "./plan-labels.ts";
import {
  cleanText,
  classifySessionlessDay,
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
  StructuredSession,
  StructuredWeek,
} from "@/lib/types";

/** Local-calendar ISO date (YYYY-MM-DD) for a Date, matching day.date strings. */
export function toISODate(date: Date): string {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/**
 * The athlete-local training-day rollover hour. The training day does not
 * advance until 04:00 local time, so a 01:00 session still belongs to the
 * previous calendar day. This mirrors the backend `/api/today` training-day
 * concept so Today and Plan Detail resolve the same current day.
 */
export const TRAINING_DAY_ROLLOVER_HOUR = 4;

/**
 * The athlete-local training-day `Date` for `now`, applying the 04:00 rollover.
 * Returns a Date at local midnight of the resolved training day so it can be fed
 * straight into `resolvePlanProgress` / `resolveCurrentDay` / `toISODate`. This
 * is the single shared entry point both Today and Plan Detail use to decide
 * "what day is it" — avoid resolving the current day from a bare `new Date()`.
 */
export function resolveTrainingDay(
  now: Date,
  rolloverHour: number = TRAINING_DAY_ROLLOVER_HOUR,
): Date {
  const resolved = new Date(now.getTime());
  if (now.getHours() < rolloverHour) {
    resolved.setDate(resolved.getDate() - 1);
  }
  resolved.setHours(0, 0, 0, 0);
  return resolved;
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
  today: Date | null,
): PlanProgress {
  const weeks = getWeeks(plan);
  const todayIso = today ? toISODate(today) : null;
  let currentWeekPos: number | null = null;
  let currentDayDate: string | null = null;

  // A null `today` (e.g. before client mount) resolves to "no current day" so
  // the server and first client render agree — never match days on a null date.
  weeks.forEach((week, weekPos) => {
    if (todayIso && getDays(week).some((day) => dayISO(day) === todayIso)) {
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
  today: Date | null,
): string | null {
  if (!today) {
    return null;
  }
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

export type WeekSessionSummary = {
  /** Days with athlete work in the app or a coach-led/contact session. */
  trainingDays: number;
  /** App-prescribed sessions with blocks/details owned by Unlxck. */
  appSessions: number;
  /** Session-less contact days owned by the athlete's coach. */
  coachLedSessions: number;
};

/**
 * Athlete-facing week counters. App sessions and coach-led days are deliberately
 * split so coach-owned contact does not look like missing app completion.
 */
export function weekSessionSummary(
  week: StructuredWeek | null | undefined,
): WeekSessionSummary {
  return getDays(week).reduce<WeekSessionSummary>(
    (acc, day) => {
      const appSessions = getSessions(day).length;
      if (appSessions > 0) {
        return {
          trainingDays: acc.trainingDays + 1,
          appSessions: acc.appSessions + appSessions,
          coachLedSessions: acc.coachLedSessions,
        };
      }

      const sessionless = classifySessionlessDay(day);
      if (sessionless.coachLed) {
        return {
          trainingDays: acc.trainingDays + 1,
          appSessions: acc.appSessions,
          coachLedSessions: acc.coachLedSessions + 1,
        };
      }

      return acc;
    },
    { trainingDays: 0, appSessions: 0, coachLedSessions: 0 },
  );
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

export type CurrentDayResolution = {
  /** The athlete-local training-day ISO date used for the match (null until the
   * client has mounted and resolved the current day). */
  trainingDayISO: string | null;
  /** Array index of the matched week, or null when today is out of camp range. */
  weekPos: number | null;
  /** Array index of the matched day within its week, or null when out of range. */
  dayPos: number | null;
  week: StructuredWeek | null;
  day: StructuredDay | null;
  /** The matched day's sessions (empty for off/rest days or when out of range). */
  sessions: StructuredSession[];
  /** "D-28" style countdown for today, or null. */
  dLabel: string | null;
  /** True when today maps to a scheduled day in the plan. */
  inRange: boolean;
};

/**
 * The single shared resolver for "which day/session is today" against a
 * structured plan. Both Today and Plan Detail call this with
 * `resolveTrainingDay(new Date())` so they can never disagree on the current
 * day. The matched day is the source of truth for its sessions — a session's own
 * date is never used to override the parent day (parent day wins).
 */
export function resolveCurrentDay(
  plan: StructuredPlan | null | undefined,
  today: Date | null,
): CurrentDayResolution {
  const trainingDayISO = today ? toISODate(today) : null;
  const weeks = getWeeks(plan);
  for (let weekPos = 0; trainingDayISO && weekPos < weeks.length; weekPos += 1) {
    const days = getDays(weeks[weekPos]);
    for (let dayPos = 0; dayPos < days.length; dayPos += 1) {
      const day = days[dayPos];
      if (dayISO(day) === trainingDayISO) {
        return {
          trainingDayISO,
          weekPos,
          dayPos,
          week: weeks[weekPos],
          day,
          sessions: getSessions(day),
          dLabel: cleanText(day.countdown_label) || deriveCountdownLabel(plan, today),
          inRange: true,
        };
      }
    }
  }
  return {
    trainingDayISO,
    weekPos: null,
    dayPos: null,
    week: null,
    day: null,
    sessions: [],
    dLabel: deriveCountdownLabel(plan, today),
    inRange: false,
  };
}

/**
 * The strongest stable identity for a session, used for completion/display keys
 * so they never drift or duplicate on title/date alone. Prefers
 * plan_id + day + session_id; falls back to plan_id + week/day/session indices
 * when stable ids are missing. The parent day owns the date, so the day's date
 * (not any per-session date) is used for the day portion.
 */
export function sessionIdentity(params: {
  planId?: string | null;
  weekPos: number;
  dayPos: number;
  sessionPos: number;
  week?: StructuredWeek | null;
  day?: StructuredDay | null;
  session?: StructuredSession | null;
}): string {
  const planKey = cleanText(params.planId) || "plan";
  const dayDate = cleanText(params.day?.date)?.slice(0, 10);
  const dayKey = dayDate || `d${params.dayPos}`;
  const sessionId = cleanText(params.session?.session_id);
  if (sessionId) {
    return `${planKey}|${dayKey}|${sessionId}`;
  }
  return `${planKey}|w${params.weekPos}|d${params.dayPos}|s${params.sessionPos}`;
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
