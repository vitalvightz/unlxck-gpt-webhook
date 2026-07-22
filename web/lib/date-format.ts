// Canonical user-facing date formatting for the whole app.
//
// One format everywhere: `EEE DD MMM YYYY` -> "Thu 02 Jul 2026".
// Locale is pinned to "en-GB" so month/day naming is stable, and the string is
// assembled from parts so the punctuation is exactly "Thu 02 Jul 2026"
// (no locale-inserted comma after the weekday) regardless of the viewer.

const DATE_ONLY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const DATE_PREFIX_PATTERN = /^(\d{4}-\d{2}-\d{2})(?:[T\s]|$)/;

/**
 * Parse a date-only ISO string (`YYYY-MM-DD`) or a full timestamp.
 *
 * Date-only displays are anchored at noon UTC so the rendered weekday/day never
 * shifts backward across a timezone boundary (the off-by-one trap). When a caller
 * uses `formatAppDate` with a timestamp-shaped value, we still use the first
 * `YYYY-MM-DD` part as a date-only value for hydration-safe rendering. Full
 * timestamps remain parsed as-is when `formatAppDateTime` needs the time.
 */
function parseAppDate(value: string, withTime: boolean): { date: Date; dateOnly: boolean } | null {
  const normalized = value.trim();
  if (!normalized) {
    return null;
  }
  const dateOnlyValue = DATE_ONLY_PATTERN.test(normalized)
    ? normalized
    : !withTime
      ? DATE_PREFIX_PATTERN.exec(normalized)?.[1]
      : undefined;
  const dateOnly = Boolean(dateOnlyValue);
  const date = new Date(dateOnly ? `${dateOnlyValue}T12:00:00Z` : normalized.replace(" ", "T"));
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return { date, dateOnly };
}

// Intl.DateTimeFormat instantiation is expensive, so cache one instance per
// distinct option combination. There are only ~4 combinations of
// (withTime, dateOnly), so the cache stays tiny and is reused across every
// render — important when formatting long lists of plans/athletes.
const formatterCache = new Map<string, Intl.DateTimeFormat>();

function getFormatter(withTime: boolean, dateOnly: boolean): Intl.DateTimeFormat {
  const key = `${withTime}-${dateOnly}`;
  let formatter = formatterCache.get(key);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat("en-GB", {
      weekday: "short",
      day: "2-digit",
      month: "short",
      year: "numeric",
      ...(withTime ? { hour: "2-digit", minute: "2-digit", hour12: false } : {}),
      ...(dateOnly ? { timeZone: "UTC" } : {}),
    });
    formatterCache.set(key, formatter);
  }
  return formatter;
}

/** The canonical date parts for a single value, or null when unparseable. */
type DateParts = { weekday: string; day: string; month: string; year: string };

function dateParts(value: string): DateParts | null {
  const parsed = parseAppDate(value, false);
  if (!parsed) {
    return null;
  }
  const parts = getFormatter(false, parsed.dateOnly).formatToParts(parsed.date);
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? "";
  return {
    weekday: get("weekday"),
    day: get("day"),
    month: get("month"),
    year: get("year"),
  };
}

function render(value: string | null | undefined, withTime: boolean): string {
  const raw = String(value ?? "");
  const parsed = parseAppDate(raw, withTime);
  if (!parsed) {
    return raw;
  }
  const formatter = getFormatter(withTime, parsed.dateOnly);
  const parts = formatter.formatToParts(parsed.date);
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? "";
  const base = `${get("weekday")} ${get("day")} ${get("month")} ${get("year")}`;
  if (!withTime) {
    return base;
  }
  return `${base}, ${get("hour")}:${get("minute")}`;
}

/** "Thu 02 Jul 2026". Returns the raw input if it can't be parsed. */
export function formatAppDate(value: string | null | undefined): string {
  return render(value, false);
}

/** "Thu 02 Jul 2026, 14:30". Returns the raw input if it can't be parsed. */
export function formatAppDateTime(value: string | null | undefined): string {
  return render(value, true);
}

/** How far out a relative label stays useful; beyond this the bare date reads
 *  fine on its own, so we return null and callers show only the date. */
const RELATIVE_DAY_HORIZON = 14;

/**
 * A short, time-relative label for a near-future date — "Today", "Tomorrow",
 * "in N days" — so a date reads as something happening soon, not just a static
 * calendar entry. Returns null (so the caller can fall back to the plain date)
 * for anything unparseable, in the past, or further out than
 * `RELATIVE_DAY_HORIZON`.
 *
 * Whole-day math: the target's UTC calendar day (date-only values are anchored
 * at noon UTC by parseAppDate) is compared against the viewer's local calendar
 * day, so "in 2 days" matches what the athlete perceives as today.
 */
export function describeRelativeDay(
  value: string | null | undefined,
  now: Date = new Date(),
): string | null {
  const parsed = parseAppDate(String(value ?? ""), false);
  if (!parsed) {
    return null;
  }
  const targetDay = Date.UTC(
    parsed.date.getUTCFullYear(),
    parsed.date.getUTCMonth(),
    parsed.date.getUTCDate(),
  );
  const nowDay = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  const diffDays = Math.round((targetDay - nowDay) / 86_400_000);
  if (diffDays < 0 || diffDays > RELATIVE_DAY_HORIZON) {
    return null;
  }
  if (diffDays === 0) {
    return "Today";
  }
  if (diffDays === 1) {
    return "Tomorrow";
  }
  return `in ${diffDays} days`;
}

/**
 * A compact, single-line date range that drops the parts the two ends share so
 * it stays on one line — the full `formatAppDate` twice is too long for tight
 * layouts (e.g. the week-overview stat tile) and wraps.
 *
 *   same month + year  -> "Wed 22 → Tue 28 Jul 2026"
 *   same year          -> "Wed 29 Jul → Sun 02 Aug 2026"
 *   different years     -> "Wed 29 Dec 2026 → Fri 01 Jan 2027"
 *
 * Degrades gracefully: if either end is missing it returns the single formatted
 * date; if either can't be parsed it falls back to the plain arrow-join so the
 * output is never worse than the previous `formatAppDate → formatAppDate`.
 */
export function formatAppDateRange(
  start: string | null | undefined,
  end: string | null | undefined,
): string {
  const rawStart = start == null ? "" : String(start).trim();
  const rawEnd = end == null ? "" : String(end).trim();
  if (!rawStart || !rawEnd) {
    return formatAppDate(rawStart || rawEnd);
  }
  const a = dateParts(rawStart);
  const b = dateParts(rawEnd);
  if (!a || !b) {
    return `${formatAppDate(rawStart)} → ${formatAppDate(rawEnd)}`;
  }
  const sameYear = a.year === b.year;
  const sameMonth = sameYear && a.month === b.month;
  const startText = sameMonth
    ? `${a.weekday} ${a.day}`
    : sameYear
      ? `${a.weekday} ${a.day} ${a.month}`
      : `${a.weekday} ${a.day} ${a.month} ${a.year}`;
  const endText = `${b.weekday} ${b.day} ${b.month} ${b.year}`;
  return `${startText} → ${endText}`;
}
