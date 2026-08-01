// Pure, defensive helpers that turn a structured_plan into the "camp map" view:
// where the athlete is in the camp (current week/day), per-week/day completion,
// a load proxy derived from day types, and the compact readiness strip. Kept
// framework-free and node:test-able, mirroring lib/structured-plan.ts. Every
// function tolerates null/partial payloads and never throws.
import { formatPlanLabel } from "./plan-labels.ts";
import {
  cleanText,
  classifySessionlessDay,
  formatCountdownLabel,
  formatSessionObjective,
  getBlocks,
  getCoachLedContactView,
  getDays,
  getDisplayableRedFlags,
  getPlanNotes,
  getSessions,
  getWeeks,
  planNoteLabel,
} from "./structured-plan.ts";
import type {
  StructuredDay,
  StructuredPlan,
  StructuredSession,
  StructuredWeek,
  TodaySessionCompletionRecord,
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
 * advance until 03:00 local time, so a 01:00 session still belongs to the
 * previous calendar day. This mirrors the backend `/api/today` training-day
 * concept so Today and Plan Detail resolve the same current day.
 */
export const TRAINING_DAY_ROLLOVER_HOUR = 3;

/**
 * The athlete-local training-day `Date` for `now`, applying the 03:00 rollover.
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

// ---------------------------------------------------------------------------
// Weekday-only (open / renewable) plan support.
//
// An open training plan has no fight date, so its days carry no calendar date —
// only a weekday ("WEEK 2 · SAT" in the plan view). Resolving "today" against
// such a plan matches on today's weekday instead of an ISO date, scoped to the
// current week of the renewable block. The current week comes from the server's
// schedule projection when available, else is derived from the same anchor the
// backend uses (the Monday of the week the plan can start training in — see
// api/services/open_plan_timeline.py).
// ---------------------------------------------------------------------------

const WEEKDAY_TOKENS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;
type WeekdayToken = (typeof WEEKDAY_TOKENS)[number];

/** Normalized short weekday ("Mon") from a day's weekday field, or null.
 * Tolerates full names ("Monday") and any casing. */
function dayWeekdayToken(day: StructuredDay | null | undefined): WeekdayToken | null {
  const token = cleanText(day?.weekday)?.slice(0, 3).toLowerCase();
  if (!token) {
    return null;
  }
  return WEEKDAY_TOKENS.find((candidate) => candidate.toLowerCase() === token) ?? null;
}

/** Short weekday token for a local Date ("Mon".."Sun"). */
function weekdayTokenFor(date: Date): WeekdayToken {
  // getDay(): 0=Sun..6=Sat -> Mon-first token list.
  return WEEKDAY_TOKENS[(date.getDay() + 6) % 7];
}

/** True when a day can use the open-plan weekday path. Legacy open plans are
 * undated; projected renewable plans carry dates but still repeat by weekday
 * inside the server-selected block week. Dated fight camps never opt in.
 *
 * A projected row is only weekday-matchable once its own date has arrived
 * (`day.date <= todayISO`). The fallback exists for a payload whose projection
 * has gone stale *behind* the clock — the block rolled over, every row is dated
 * in the past, and the weekly rhythm still holds. A row dated in the FUTURE is
 * the opposite situation: the block simply has not started yet (an open plan
 * created mid-week anchors to the following Monday), so today is genuinely not a
 * plan day. Matching it there marked a future row "Today" and relabelled it with
 * today's real date, dropping a past date into the middle of an ascending week
 * ("THU 06 AUG / FRI 31 JUL / SAT 08 AUG"). */
function isWeekdayMatchableDay(
  day: StructuredDay | null | undefined,
  allowDatedDays = false,
  todayISO: string | null = null,
): boolean {
  if (dayWeekdayToken(day) === null) {
    return false;
  }
  const iso = dayISO(day);
  if (iso === null) {
    return true;
  }
  return allowDatedDays && todayISO !== null && iso <= todayISO;
}

export type OpenScheduleHints = {
  /** Server-computed 1-based week number inside the current renewable block
   * (schedule_context.current_week_number). Wins when present. */
  currentWeekNumber?: number | null;
  /** Server anchor date (schedule_context.anchor_date). */
  anchorDate?: string | null;
  /** Plan creation timestamp; the anchor is derived from it when the server did
   * not provide one (the creation week's Monday for a Mon-Thu plan, the coming
   * Monday for a Fri-Sun one). */
  createdAt?: string | null;
};

/** Local-noon ms for the date portion of an ISO string, or null. Noon keeps the
 * day-difference math DST-safe. */
function isoToNoonMs(value: string | null | undefined): number | null {
  const iso = cleanText(value)?.slice(0, 10);
  if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    return null;
  }
  const ms = new Date(`${iso}T12:00:00`).getTime();
  return Number.isNaN(ms) ? null : ms;
}

/**
 * The 1-based week number of the renewable block containing `today`, for a
 * weekday-only open plan. Mirrors the backend projection
 * (api/services/open_plan_timeline.py): an explicit server week number wins;
 * otherwise the week is counted from the anchor (server-provided, else derived
 * from plan creation — the Monday of the creation week for a Mon-Thu plan, the
 * coming Monday for a Fri-Sun one), wrapping every `weekCount` weeks so the
 * block renews indefinitely. Days before the anchor belong to week 1.
 * Returns null when there is no week count, no today, or no usable anchor.
 */
export function resolveOpenPlanWeekNumber(
  plan: StructuredPlan | null | undefined,
  today: Date | null,
  hints?: OpenScheduleHints | null,
): number | null {
  const weekCount = getWeeks(plan).length;
  if (!weekCount || !today) {
    return null;
  }

  const explicit = hints?.currentWeekNumber;
  if (typeof explicit === "number" && Number.isFinite(explicit) && explicit >= 1) {
    return Math.min(Math.trunc(explicit), weekCount);
  }

  let anchorMs = isoToNoonMs(hints?.anchorDate);
  if (anchorMs === null) {
    const createdMs = isoToNoonMs(hints?.createdAt);
    if (createdMs !== null) {
      // Monday of the week the plan can start training in: the creation week for
      // a Mon-Thu plan, the next one for Fri-Sun. Same shift-then-truncate the
      // backend uses (Python weekday(): Mon=0).
      const shiftedMs = createdMs + 3 * 86_400_000;
      const shiftedWeekday = (new Date(shiftedMs).getDay() + 6) % 7;
      anchorMs = shiftedMs - shiftedWeekday * 86_400_000;
    }
  }
  if (anchorMs === null) {
    return null;
  }

  const todayMs = new Date(today.getFullYear(), today.getMonth(), today.getDate(), 12).getTime();
  const elapsedDays = Math.round((todayMs - anchorMs) / 86_400_000);
  if (elapsedDays < 0) {
    return 1;
  }
  return (Math.floor(elapsedDays / 7) % weekCount) + 1;
}

type WeekdayOnlyMatch = {
  weekPos: number;
  dayPos: number;
  week: StructuredWeek;
  day: StructuredDay;
};

/**
 * Match today's weekday against a plan's weekday-only days. The preferred week
 * (1-based `openWeekNumber`, when known) is searched first so the block's
 * current week owns the match; any week with that weekday is the fallback, so
 * an open plan still resolves when no anchor is available (all weeks of an
 * open block share the same weekly rhythm). Dated days only match here once
 * their own date has passed (see `isWeekdayMatchableDay`), so a plan whose block
 * starts in the future stays out of range instead of stamping "Today" onto a row
 * that has not arrived yet.
 */
function findWeekdayDay(
  weeks: StructuredWeek[],
  today: Date,
  openWeekNumber?: number | null,
  allowDatedDays = false,
): WeekdayOnlyMatch | null {
  const target = weekdayTokenFor(today);
  const todayISO = toISODate(today);
  const matchIn = (weekPos: number): WeekdayOnlyMatch | null => {
    const days = getDays(weeks[weekPos]);
    for (let dayPos = 0; dayPos < days.length; dayPos += 1) {
      const day = days[dayPos];
      if (isWeekdayMatchableDay(day, allowDatedDays, todayISO) && dayWeekdayToken(day) === target) {
        return { weekPos, dayPos, week: weeks[weekPos], day };
      }
    }
    return null;
  };

  const preferred =
    typeof openWeekNumber === "number" && Number.isFinite(openWeekNumber) && openWeekNumber >= 1
      ? Math.min(Math.trunc(openWeekNumber), weeks.length) - 1
      : null;
  if (preferred !== null) {
    const match = matchIn(preferred);
    if (match) {
      return match;
    }
  }
  for (let weekPos = 0; weekPos < weeks.length; weekPos += 1) {
    if (weekPos === preferred) {
      continue;
    }
    const match = matchIn(weekPos);
    if (match) {
      return match;
    }
  }
  return null;
}

export type PlanMatchType = "calendar" | "weekday";

export type PlanProgress = {
  weekCount: number;
  /** Array index of the week containing today, or null when out of camp range. */
  currentWeekPos: number | null;
  /** Stored ISO date of today's exact calendar row, or null for a weekday
   * fallback or when out of range. */
  currentDayDate: string | null;
  /** Array index of today's day within its week, or null when out of range. */
  currentDayPos: number | null;
  /** The athlete-local date being resolved, including for weekday fallbacks. */
  trainingDayISO: string | null;
  /** Whether the plan row matched its stored date or only its recurring weekday. */
  matchType: PlanMatchType | null;
  /** "D-28" style countdown for today (from the day, else derived), or null. */
  dLabel: string | null;
};

/**
 * Resolve where the athlete is in the camp relative to `today`. Matches today to
 * a day by calendar date; weekday-only days (open / renewable plans) fall back
 * to matching today's weekday, scoped by `options.openWeekNumber` — the same
 * rules as `resolveCurrentDay`. When today matches nothing the current markers
 * are null (callers default selection to the first week) and the countdown
 * label is derived from the event date when available.
 */
export function resolvePlanProgress(
  plan: StructuredPlan | null | undefined,
  today: Date | null,
  options?: { openWeekNumber?: number | null; allowDatedWeekdayMatch?: boolean },
): PlanProgress {
  const weeks = getWeeks(plan);
  const todayIso = today ? toISODate(today) : null;
  let currentWeekPos: number | null = null;
  let currentDayDate: string | null = null;
  let currentDayPos: number | null = null;
  let matchType: PlanMatchType | null = null;

  // A null `today` (e.g. before client mount) resolves to "no current day" so
  // the server and first client render agree — never match days on a null date.
  weeks.forEach((week, weekPos) => {
    getDays(week).forEach((day, dayPos) => {
      if (todayIso && dayISO(day) === todayIso) {
        currentWeekPos = weekPos;
        currentDayDate = todayIso;
        currentDayPos = dayPos;
        matchType = "calendar";
      }
    });
  });

  if (currentWeekPos === null && today) {
    const weekdayMatch = findWeekdayDay(
      weeks,
      today,
      options?.openWeekNumber,
      options?.allowDatedWeekdayMatch,
    );
    if (weekdayMatch) {
      currentWeekPos = weekdayMatch.weekPos;
      currentDayPos = weekdayMatch.dayPos;
      matchType = "weekday";
    }
  }

  const currentDay = findDayByISO(plan, currentDayDate);
  const dLabel = formatCountdownLabel(currentDay?.countdown_label) || deriveCountdownLabel(plan, today);

  return {
    weekCount: weeks.length,
    currentWeekPos,
    currentDayDate,
    currentDayPos,
    trainingDayISO: todayIso,
    matchType,
    dLabel,
  };
}

export type CampProgress = {
  /** 0-100 timeline completion from camp start to fight day. */
  pct: number;
  /** "Week 6 of 8", or null when the week count is unknown. */
  weekLabel: string | null;
  /** "D-7" style countdown for today, or null. */
  dLabel: string | null;
};

/** Local-midnight ms for a plain "YYYY-MM-DD", parsed at midnight to align with today's normalized training day. */
function isoToMs(iso: string | null): number | null {
  if (!iso || !/^\\d{4}-\\d{2}-\\d{2}$/.test(iso.slice(0, 10))) {
    return null;
  }
  const ms = new Date(`${iso.slice(0, 10)}T00:00:00`).getTime();
  return Number.isNaN(ms) ? null : ms;
}

/**
 * Camp timeline progress for a glanceable "how far through camp" bar, shared by
 * Today and Overview so the two can never disagree. Progress is a pure timeline
 * measure — today's position between the first scheduled day (camp start) and
 * fight day — so it stays stable even when today doesn't match a scheduled day
 * (e.g. a rest/preview day). Returns null when there isn't enough of a plan to
 * draw a meaningful bar, so callers can simply hide it.
 */
export function getCampProgress(
  plan: StructuredPlan | null | undefined,
  today: Date | null,
): CampProgress | null {
  const weeks = getWeeks(plan);
  if (!weeks.length || !today) {
    return null;
  }

  // Camp span: earliest scheduled day → fight day (falling back to the last
  // scheduled day when the event date is missing).
  const dayMsValues: number[] = [];
  weeks.forEach((week) => {
    getDays(week).forEach((day) => {
      const ms = isoToMs(dayISO(day));
      if (ms !== null) {
        dayMsValues.push(ms);
      }
    });
  });
  if (!dayMsValues.length) {
    return null;
  }
  const startMs = Math.min(...dayMsValues);
  const eventIso =
    cleanText(plan?.event_context?.fight_date) || cleanText(plan?.event_context?.match_date);
  const endMs = isoToMs(eventIso) ?? Math.max(...dayMsValues);
  const todayMs = today.getTime();

  const span = endMs - startMs;
  const pct = span > 0 ? Math.max(0, Math.min(100, ((todayMs - startMs) / span) * 100)) : 0;

  const progress = resolvePlanProgress(plan, today);
  const weekCount = progress.weekCount;
  // Prefer the exact matched week; otherwise estimate from the timeline so a
  // rest/preview day still reads a sensible "Week X of Y".
  const currentWeek =
    progress.currentWeekPos != null
      ? progress.currentWeekPos + 1
      : weekCount
        ? Math.min(weekCount, Math.max(1, Math.ceil((pct / 100) * weekCount)))
        : null;
  const weekLabel = weekCount && currentWeek ? `Week ${currentWeek} of ${weekCount}` : null;

  return { pct, weekLabel, dLabel: progress.dLabel };
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
  return `D-${diffDays}`;
}

export type Completion = { done: number; total: number };
const TERMINAL_SESSION_COMPLETION_STATUSES = new Set(["done", "modified", "skipped"]);

/** Sessions marked done over total sessions across all of a week's days. */
export function weekCompletion(
  week: StructuredWeek | null | undefined,
  index?: CompletionIndex,
): Completion {
  return getDays(week).reduce<Completion>(
    (acc, day) => {
      const dayDone = dayCompletion(day, index);
      return { done: acc.done + dayDone.done, total: acc.total + dayDone.total };
    },
    { done: 0, total: 0 },
  );
}

/** Sessions marked done over total sessions for a single day. When a live
 * completion index is supplied, real logged statuses win over the static
 * `completion_status` baked into the plan JSON at generation time (always
 * "not_started"), so the tag can actually light up. */
export function dayCompletion(
  day: StructuredDay | null | undefined,
  index?: CompletionIndex,
): Completion {
  const sessions = getSessions(day);
  const done = sessions.filter((session) => {
    const live = index ? completionForSession(index, day, session) : undefined;
    const status = live?.status ?? cleanText(session.completion_status)?.toLowerCase();
    return status === "done" || status === "modified";
  }).length;
  return { done, total: sessions.length };
}

// ---------------------------------------------------------------------------
// Live session-completion merge: index rows from /api/plans/{id}/completions
// and resolve each plan card's real status (done/modified/skipped/missed).
// ---------------------------------------------------------------------------

export type CompletionIndex = Map<string, TodaySessionCompletionRecord>;

const completionKey = (trainingDay: string, sessionId: string): string =>
  `${trainingDay}|${sessionId}`;

/** Index completion rows by `training_day|session_id` for O(1) card lookups. */
export function buildCompletionIndex(
  rows: readonly TodaySessionCompletionRecord[] | null | undefined,
): CompletionIndex {
  const index: CompletionIndex = new Map();
  for (const row of rows ?? []) {
    const day = cleanText(row.training_day)?.slice(0, 10);
    const sessionId = cleanText(row.session_id);
    if (day && sessionId) {
      index.set(completionKey(day, sessionId), row);
    }
  }
  return index;
}

/** The day's primary (loggable) session, mirroring the backend's
 * `_select_structured_primary_session`: first session with executable blocks,
 * else the first session. */
export function primarySessionOf(
  day: StructuredDay | null | undefined,
): StructuredSession | null {
  const sessions = getSessions(day);
  if (sessions.length === 0) {
    return null;
  }
  return sessions.find((session) => getBlocks(session).length > 0) ?? sessions[0];
}

/**
 * The backend id a completion row would carry for this session, or null when
 * the session can never be logged. Mirrors the server fallback
 * `session_id = session.session_id || day_date` — which applies to the day's
 * primary session only; a secondary id-less session has no completion identity.
 */
export function completionSessionId(
  day: StructuredDay | null | undefined,
  session: StructuredSession | null | undefined,
): string | null {
  const explicit = cleanText(session?.session_id);
  if (explicit) {
    return explicit;
  }
  const iso = dayISO(day);
  if (!iso) {
    return null;
  }
  return session == null || session === primarySessionOf(day) ? iso : null;
}

/** The live completion row for one plan-card session, if any. */
export function completionForSession(
  index: CompletionIndex,
  day: StructuredDay | null | undefined,
  session: StructuredSession | null | undefined,
): TodaySessionCompletionRecord | undefined {
  const iso = dayISO(day);
  const sessionId = completionSessionId(day, session);
  if (!iso || !sessionId) {
    return undefined;
  }
  return index.get(completionKey(iso, sessionId));
}

export type SessionDisplayState =
  | "done"
  | "modified"
  | "skipped"
  | "missed"
  | "pending"
  | "upcoming";

export type SessionDisplayStatus = {
  state: SessionDisplayState;
  /** green = done, amber = modified, red = skipped/missed, neutral otherwise. */
  tone: "green" | "amber" | "red" | "neutral";
  label: string;
};

/**
 * Resolve what a plan card should show for a session given its live completion
 * row (if any) and the server-authoritative current training day. A past day
 * with no terminal log — including one only ever `started` — reads as Missed.
 */
export function getSessionDisplayStatus(
  completion: TodaySessionCompletionRecord | undefined,
  dayIso: string | null,
  currentDayIso: string | null,
): SessionDisplayStatus {
  const status = completion?.status;
  if (status === "done") {
    return { state: "done", tone: "green", label: "Done" };
  }
  if (status === "modified") {
    return { state: "modified", tone: "amber", label: "Modified" };
  }
  if (status === "skipped") {
    return { state: "skipped", tone: "red", label: "Skipped" };
  }
  const isPast = Boolean(dayIso && currentDayIso && dayIso < currentDayIso);
  if (isPast) {
    return { state: "missed", tone: "red", label: "Missed" };
  }
  return dayIso && currentDayIso && dayIso === currentDayIso
    ? { state: "pending", tone: "neutral", label: "" }
    : { state: "upcoming", tone: "neutral", label: "" };
}

/** How many days back a session may still be logged after the fact. */
export const RETRO_LOG_WINDOW_DAYS = 7;

/** True when a past day is still inside the retro-log back-fill window. */
export function canRetroLog(dayIso: string | null, currentDayIso: string | null): boolean {
  if (!dayIso || !currentDayIso || dayIso >= currentDayIso) {
    return false;
  }
  const day = new Date(`${dayIso}T12:00:00`);
  const current = new Date(`${currentDayIso}T12:00:00`);
  if (Number.isNaN(day.getTime()) || Number.isNaN(current.getTime())) {
    return false;
  }
  const diffDays = Math.round((current.getTime() - day.getTime()) / (24 * 60 * 60 * 1000));
  return diffDays <= RETRO_LOG_WINDOW_DAYS;
}

function isSessionTerminal(session: StructuredSession | null | undefined): boolean {
  return TERMINAL_SESSION_COMPLETION_STATUSES.has(
    cleanText(session?.completion_status)?.toLowerCase() ?? "",
  );
}

function dateFromDay(day: StructuredDay | null | undefined): Date | null {
  const iso = dayISO(day);
  if (!iso) {
    return null;
  }
  const parsed = new Date(`${iso}T12:00:00`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

/**
 * Correct a backend-provided "next session" focus against the card order the
 * athlete can actually see. Once Today is logged, Plan Detail should advance to
 * the first future unfinished app-session card in rendered order; only when
 * there is no such app card do coach-led/sessionless days get the marker.
 */
export function resolveNextPlanFocusDay(
  plan: StructuredPlan | null | undefined,
  trainingDay: Date | null,
  fallbackFocusDay: Date | null | undefined,
  options?: { openWeekNumber?: number | null; allowDatedWeekdayMatch?: boolean },
): Date | undefined {
  if (!trainingDay || !fallbackFocusDay) {
    return fallbackFocusDay ?? undefined;
  }
  const current = resolveCurrentDay(plan, trainingDay, options);
  if (current.weekPos == null || current.dayPos == null) {
    return fallbackFocusDay;
  }

  const weeks = getWeeks(plan);
  const futureDays: StructuredDay[] = [];
  for (let weekPos = current.weekPos; weekPos < weeks.length; weekPos += 1) {
    const days = getDays(weeks[weekPos]);
    const startDayPos = weekPos === current.weekPos ? current.dayPos + 1 : 0;
    for (let dayPos = startDayPos; dayPos < days.length; dayPos += 1) {
      futureDays.push(days[dayPos]!);
    }
  }

  const nextAppDay = futureDays.find((day) => {
    const sessions = getSessions(day);
    return sessions.length > 0 && sessions.some((session) => !isSessionTerminal(session));
  });
  const nextCoachLedDay = futureDays.find((day) => {
    return getSessions(day).length === 0 && classifySessionlessDay(day).coachLed;
  });
  return dateFromDay(nextAppDay ?? nextCoachLedDay) ?? fallbackFocusDay;
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

const DAY_LOAD_POINTS: Record<string, number> = {
  off: 0,
  rest: 0,
  recovery: 0.5,
  low: 1,
  technical: 1.5,
  moderate: 2,
  medium: 2,
  high: 3,
  hard: 3,
  hard_spar: 3,
  sparring: 3,
};

function normalizedLoadToken(value: unknown): string | null {
  return cleanText(value)?.toLowerCase().replace(/[\s-]+/g, "_") ?? null;
}

function dayTypeLoadPoints(day: StructuredDay | null | undefined): number {
  const token = normalizedLoadToken(day?.day_type);
  return token ? DAY_LOAD_POINTS[token] ?? 0 : 0;
}

const LOW_LOAD_SESSION_TYPES = new Set(["primer", "recovery", "rehab", "support_insert"]);
const LOW_LOAD_BLOCK_TYPES = new Set([
  "preparation",
  "mobility_activation",
  "cooldown_recovery",
  "nutrition",
  "mindset",
  "rehab",
]);
const LOADED_SESSION_TYPES = new Set([
  "strength_power",
  "conditioning",
  "sparring",
  "fight_or_match",
  "mixed",
]);
const SUPPORT_SESSION_TITLE_RE =
  /\b(?:cue card|fight tactical watch|self-review cues?|neural visualization|breathing reset|recovery reset|sleep downshift|mobility|movement quality check|technical shadow rhythm|footwork walkthrough|joint prep|walk flush|shadowboxing aerobic flow|footwork rhythm flush|skipping flush|jog flush)\b/;

/** True when a session is a low-cost filler or mobility/recovery-only touch. */
function isLowLoadSupportSession(session: StructuredSession | null | undefined): boolean {
  const sessionType = normalizedLoadToken(session?.session_type);
  if (sessionType && LOW_LOAD_SESSION_TYPES.has(sessionType)) {
    return true;
  }

  const blocks = getBlocks(session);
  if (
    blocks.length > 0 &&
    blocks.every((block) => {
      const blockType = normalizedLoadToken(block.block_type);
      return Boolean(blockType && LOW_LOAD_BLOCK_TYPES.has(blockType));
    })
  ) {
    return true;
  }

  // Distinctive generated filler titles survive structured-plan normalization.
  // Do not let a generic mobility mention override an explicitly loaded session.
  if (sessionType && LOADED_SESSION_TYPES.has(sessionType)) {
    return false;
  }
  const title = cleanText(session?.title)?.toLowerCase() ?? "";
  return blocks.length === 0 && SUPPORT_SESSION_TITLE_RE.test(title);
}

function sessionLoadPoints(session: StructuredSession | null | undefined): number {
  if (isLowLoadSupportSession(session)) {
    return 1;
  }

  const text = [
    session?.session_type,
    session?.title,
    session?.objective,
    session?.primary_stressor,
    session?.cns_demand,
    session?.impact_level,
  ]
    .map((value) => cleanText(value)?.toLowerCase())
    .filter(Boolean)
    .join(" ");

  if (/\b(hard|spar|sprint|speed|power|max|explosive|hiit|anaerobic)\b/.test(text)) {
    return 3;
  }

  if (/\b(strength|conditioning|tempo|moderate|repeat)\b/.test(text)) {
    return 2;
  }

  if (getBlocks(session).length === 0 && /\b(rehab|prehab|mobility|recovery|easy|low)\b/.test(text)) {
    return 1;
  }

  return 1.5;
}

function appDayLoadPoints(day: StructuredDay): number {
  const sessions = getSessions(day);
  if (sessions.length === 0) {
    return 0;
  }

  const sessionScores = sessions.map(sessionLoadPoints);
  const sessionMax = Math.max(...sessionScores);
  const loadBearingSessions = sessionScores.filter((score) => score > 1).length;

  // Extra load-bearing sessions add volume. Fillers and mobility-only inserts do
  // not raise the day score or inherit an incorrectly high day_type badge.
  const extraSessionVolume = Math.max(0, loadBearingSessions - 1) * 0.75;
  const dayTypeFloor = loadBearingSessions > 0 ? dayTypeLoadPoints(day) : 0;
  const coachLedFloor = coachLedDayLoadPoints(day);

  return Math.min(4, Math.max(dayTypeFloor, coachLedFloor, sessionMax, 1) + extraSessionVolume);
}

function coachLedDayLoadPoints(day: StructuredDay): number {
  const coachLedContact = getCoachLedContactView(day);
  if (coachLedContact?.kind === "sparring") {
    return 3;
  }
  if (coachLedContact?.kind === "technical") {
    return 1.5;
  }
  if (coachLedContact) {
    return 2;
  }

  const sessionless = classifySessionlessDay(day);

  if (!sessionless.coachLed) {
    return 0;
  }

  if (sessionless.kind === "sparring") {
    return 3;
  }

  if (sessionless.kind === "technical") {
    return 1.5;
  }

  return 2;
}

/**
 * Athlete-facing weekly load label.
 *
 * This is a weekly burden proxy, not the hardest single day. One high/intense
 * touch inside a low-volume taper week should not make the whole week read High.
 */
export function weekLoadProxy(week: StructuredWeek | null | undefined): string | null {
  const days = getDays(week);
  if (days.length === 0) {
    return null;
  }

  const trainingScores = days
    .map((day) => {
      const appScore = appDayLoadPoints(day);
      if (appScore > 0) {
        return appScore;
      }

      const coachScore = coachLedDayLoadPoints(day);
      if (coachScore > 0) {
        return coachScore;
      }

      return dayTypeLoadPoints(day);
    })
    .filter((score) => score > 0);

  if (trainingScores.length === 0) {
    return "Rest";
  }

  const total = trainingScores.reduce((sum, score) => sum + score, 0);
  const highDays = trainingScores.filter((score) => score >= 3).length;
  const loadBearingDays = trainingScores.filter((score) => score > 1).length;
  const isTaper = /\btaper\b/i.test(cleanText(week?.phase_label) ?? "");

  if (total >= 8 || highDays >= 2 || loadBearingDays >= 5) {
    return isTaper ? "Moderate" : "High";
  }

  if (total >= 4 || loadBearingDays >= 3) {
    return "Moderate";
  }

  return "Low";
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
  /** Whether the plan row matched its stored date or only its recurring weekday. */
  matchType: PlanMatchType | null;
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
 *
 * Dated camps match on the calendar date. When no date matches, open / renewable
 * plans may match their recurring rows on today's weekday ("WEEK 2 · SAT"), with
 * `options.openWeekNumber` (see `resolveOpenPlanWeekNumber`) picking the week
 * of the renewable block. That fallback is explicit in `matchType`, so callers
 * never mistake a projected row date for the live training day. Dated fight
 * camps never use this fallback and remain out of range when their dates miss.
 */
export function resolveCurrentDay(
  plan: StructuredPlan | null | undefined,
  today: Date | null,
  options?: { openWeekNumber?: number | null; allowDatedWeekdayMatch?: boolean },
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
          matchType: "calendar",
          weekPos,
          dayPos,
          week: weeks[weekPos],
          day,
          sessions: getSessions(day),
          dLabel: formatCountdownLabel(day.countdown_label) || deriveCountdownLabel(plan, today),
          inRange: true,
        };
      }
    }
  }

  const weekdayMatch = today
    ? findWeekdayDay(
        weeks,
        today,
        options?.openWeekNumber,
        options?.allowDatedWeekdayMatch,
      )
    : null;
  if (weekdayMatch) {
    return {
      trainingDayISO,
      matchType: "weekday",
      weekPos: weekdayMatch.weekPos,
      dayPos: weekdayMatch.dayPos,
      week: weekdayMatch.week,
      day: weekdayMatch.day,
      sessions: getSessions(weekdayMatch.day),
      dLabel: formatCountdownLabel(weekdayMatch.day.countdown_label) || deriveCountdownLabel(plan, today),
      inRange: true,
    };
  }

  return {
    trainingDayISO,
    matchType: null,
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
  focus: string | null;
  risk: string | null;
  load: string | null;
};

/**
 * The plan page's lighter "camp readiness" strip: focus, injury watch and weekly
 * load.
 *
 * It deliberately does NOT carry the exact "train as planned / modify / pull
 * back" call. This app has a split architecture — Today owns execution and the
 * exact readiness decision; the plan page is the camp map. So the strip surfaces
 * risk *context* without turning the plan page into a second Today screen.
 * Phase/camp status is intentionally left out here too — the CampStatusLine
 * already carries it, so the strip stays focused on readiness context only.
 *
 * An explicit `plan.readiness_snapshot` always wins when a field is present; the
 * rest is derived so the strip is useful even before generation emits a
 * snapshot:
 *   - Focus:        snapshot.focus → today_card.headline → first session objective.
 *   - Injury watch: snapshot.injury_watch → a SHORT cue from the injury /
 *                   weight-cut note labels (never the full stop/report sentence,
 *                   which stays in the Red Flags card).
 *   - Weekly load:  snapshot.weekly_load → weekLoadProxy(focusWeek).
 *
 * Every field is nullable so callers render only the cards with data — no
 * invented HRV/recovery scores.
 */
export function getReadinessStrip(
  plan: StructuredPlan | null | undefined,
  currentDay: StructuredDay | null | undefined,
  focusWeek: StructuredWeek | null | undefined,
): ReadinessStrip {
  const snapshot = plan?.readiness_snapshot;
  const card = currentDay?.today_card;

  let focus = cleanText(snapshot?.focus) || cleanText(card?.headline);
  if (!focus) {
    const firstSession = getSessions(currentDay)[0];
    focus = formatSessionObjective(firstSession?.objective) || cleanText(firstSession?.title);
  }

  // Injury watch is a SHORT cue — the watch areas only, never the full
  // stop/report sentence. Those live canonically in the Red Flags card right
  // below the strip, so repeating the whole sentence here was pure duplication.
  // Derived from the plan's injury / weight-cut note labels, with a pointer to
  // the Red Flags card when stop/report rules exist.
  let risk = cleanText(snapshot?.injury_watch);
  if (!risk) {
    const watchAreas = Array.from(
      new Set(
        getPlanNotes(plan)
          .filter((note) => note.category === "injury" || note.category === "weight_cut")
          .map((note) => planNoteLabel(note))
      )
    );
    if (watchAreas.length > 0) {
      const cue = watchAreas.join(" · ");
      risk = getDisplayableRedFlags(plan).length > 0 ? `${cue} — see red flags` : cue;
    }
  }

  const load = cleanText(snapshot?.weekly_load) || weekLoadProxy(focusWeek);

  return { focus, risk, load };
}
