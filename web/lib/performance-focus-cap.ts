import focusPolicy from "../../shared/performance-focus-policy.json";

type PerformanceFocusCapWindow = {
  maxDaysUntilFight: number;
  maxSelections: number;
  windowLabel: string;
  reason: string;
};

export type PerformanceFocusCap = {
  daysUntilFight: number;
  weeksOut: number;
  maxSelections: number;
  windowLabel: string;
  reason: string;
};

export type PerformanceFocusValidation = {
  cap: PerformanceFocusCap | null;
  totalSelections: number;
  excessSelections: number;
  isOverCap: boolean;
  errorMessage: string | null;
};

// The open-plan cap, the fight-date windows and the over-cap message live in
// shared/performance-focus-policy.json, which api/performance_focus.py reads
// too: the server enforces the same cap this form blocks submit at.
const OPEN_PLAN_FOCUS_CAP: PerformanceFocusCap = {
  daysUntilFight: Number.POSITIVE_INFINITY,
  weeksOut: Number.POSITIVE_INFINITY,
  maxSelections: focusPolicy.open_plan.max_selections,
  windowLabel: focusPolicy.open_plan.window_label,
  reason: focusPolicy.open_plan.reason,
};

// The last window is open-ended (`max_days_until_fight: null`).
const PERFORMANCE_FOCUS_CAP_WINDOWS: PerformanceFocusCapWindow[] = focusPolicy.windows.map((entry) => ({
  maxDaysUntilFight: entry.max_days_until_fight ?? Number.POSITIVE_INFINITY,
  maxSelections: entry.max_selections,
  windowLabel: entry.window_label,
  reason: entry.reason,
}));

function parseDateOnly(value: string | null | undefined): { year: number; month: number; day: number } | null {
  const match = (value ?? "").trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) {
    return null;
  }

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) {
    return null;
  }

  const candidate = new Date(Date.UTC(year, month - 1, day));
  if (
    Number.isNaN(candidate.getTime())
    || candidate.getUTCFullYear() !== year
    || candidate.getUTCMonth() !== month - 1
    || candidate.getUTCDate() !== day
  ) {
    return null;
  }

  return { year, month, day };
}

function getCalendarDateParts(date: Date, timeZone?: string | null): { year: number; month: number; day: number } {
  const buildFormatter = (nextTimeZone?: string) => new Intl.DateTimeFormat("en-CA", {
    timeZone: nextTimeZone || undefined,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });

  let formatter: Intl.DateTimeFormat;
  try {
    formatter = buildFormatter(timeZone || undefined);
  } catch {
    formatter = buildFormatter();
  }

  const parts = formatter.formatToParts(date);
  const year = Number(parts.find((part) => part.type === "year")?.value ?? "");
  const month = Number(parts.find((part) => part.type === "month")?.value ?? "");
  const day = Number(parts.find((part) => part.type === "day")?.value ?? "");

  return { year, month, day };
}

export function getPerformanceFocusCap(
  fightDate: string | null | undefined,
  options?: { now?: Date; timeZone?: string | null },
): PerformanceFocusCap | null {
  const parsedFightDate = parseDateOnly(fightDate);
  if (!parsedFightDate) {
    return OPEN_PLAN_FOCUS_CAP;
  }

  const referenceDate = options?.now ?? new Date();
  const today = getCalendarDateParts(referenceDate, options?.timeZone);
  const fightDayUtc = Date.UTC(parsedFightDate.year, parsedFightDate.month - 1, parsedFightDate.day);
  const todayUtc = Date.UTC(today.year, today.month - 1, today.day);
  const daysUntilFight = Math.floor((fightDayUtc - todayUtc) / 86_400_000);
  if (daysUntilFight < 0) {
    return null;
  }

  const window = PERFORMANCE_FOCUS_CAP_WINDOWS.find((entry) => daysUntilFight <= entry.maxDaysUntilFight)
    ?? PERFORMANCE_FOCUS_CAP_WINDOWS[PERFORMANCE_FOCUS_CAP_WINDOWS.length - 1];

  return {
    daysUntilFight,
    weeksOut: Math.max(1, Math.floor(daysUntilFight / 7)),
    maxSelections: window.maxSelections,
    windowLabel: window.windowLabel,
    reason: window.reason,
  };
}

// Short copy for tight surfaces (disabled chips, hover hints) where space is limited.
export const FOCUS_CAP_DISABLED_REASON = "Free one focus slot to add this.";

// Detailed copy for submit-blocking errors where the user needs the cap and the exact excess.
function buildPerformanceFocusCapErrorMessage(maxSelections: number, excessSelections: number): string {
  const values: Record<string, string> = {
    max_selections: String(maxSelections),
    excess_selections: String(excessSelections),
    selection_label: excessSelections === 1 ? "selection" : "selections",
  };
  return focusPolicy.over_cap_message.replace(/\{(\w+)\}/g, (placeholder, key: string) => values[key] ?? placeholder);
}

export function validatePerformanceFocusSelections(
  fightDate: string | null | undefined,
  selections: {
    keyGoals: string[];
    weakAreas: string[];
  },
  options?: { now?: Date; timeZone?: string | null },
): PerformanceFocusValidation {
  const cap = getPerformanceFocusCap(fightDate, options);
  const totalSelections = selections.keyGoals.length + selections.weakAreas.length;
  const excessSelections = cap ? Math.max(totalSelections - cap.maxSelections, 0) : 0;

  return {
    cap,
    totalSelections,
    excessSelections,
    isOverCap: excessSelections > 0,
    errorMessage: cap && excessSelections > 0
      ? buildPerformanceFocusCapErrorMessage(cap.maxSelections, excessSelections)
      : null,
  };
}
