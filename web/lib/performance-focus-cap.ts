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

const PERFORMANCE_FOCUS_CAP_WINDOWS: PerformanceFocusCapWindow[] = [
  {
    maxDaysUntilFight: 7,
    maxSelections: 3,
    windowLabel: "Fight week",
    reason: "Fight-week plans stay extremely selective so sharpness and readiness do not get buried under too many priorities.",
  },
  {
    maxDaysUntilFight: 21,
    maxSelections: 4,
    windowLabel: "Ultra-short camp",
    reason: "Ultra-short camps need a tight focus so the plan does not spread work across too many targets at once.",
  },
  {
    maxDaysUntilFight: 42,
    maxSelections: 5,
    windowLabel: "Short camp",
    reason: "Short camps can cover a few parallel priorities, but they still need selectivity to keep sessions coherent.",
  },
  {
    maxDaysUntilFight: 70,
    maxSelections: 6,
    windowLabel: "Mid-length camp",
    reason: "Mid-length camps have room for a broader focus without losing the main thread of the plan.",
  },
  {
    maxDaysUntilFight: Number.POSITIVE_INFINITY,
    maxSelections: 7,
    windowLabel: "Long camp",
    reason: "Longer camps have enough runway to support more development themes without diluting the plan.",
  },
];

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
    return null;
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

function buildPerformanceFocusCapErrorMessage(maxSelections: number, excessSelections: number): string {
  const selectionLabel = excessSelections === 1 ? "selection" : "selections";
  return `This camp allows ${maxSelections} total focus picks. Remove ${excessSelections} goal or weak-area ${selectionLabel} before generating.`;
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
