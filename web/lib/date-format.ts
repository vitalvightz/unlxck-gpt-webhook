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
