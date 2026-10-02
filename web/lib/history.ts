// Pure display helpers for the /history page (Sessions / Sparring /
// Check-ins / Injuries). Kept free of React so the tone and label mapping is unit-testable
// with node:test.

import type { TodayDecisionTone } from "@/lib/today";
import type {
  InjuryFlagRecord,
  SparringHeadContact,
  SparringIntensity,
  SparringLogRecord,
  SparringPlannedIntensity,
  SparringWindowSummary,
  TodayCheckinHistoryRecord,
  TodayCompletionStatus,
  TodayRecommendationState,
} from "@/lib/types";

// Colour contract (user-approved): done = green, modified = amber,
// skipped = red, anything unfinished = neutral.
export function sessionStatusTone(status: TodayCompletionStatus): TodayDecisionTone {
  if (status === "done") {
    return "green";
  }
  if (status === "modified") {
    return "amber";
  }
  if (status === "skipped") {
    return "red";
  }
  return "neutral";
}

export function sessionStatusLabel(status: TodayCompletionStatus): string {
  const labels: Record<TodayCompletionStatus, string> = {
    not_started: "Not started",
    started: "Started",
    done: "Done",
    modified: "Modified",
    skipped: "Skipped",
  };
  return labels[status] ?? "Not started";
}

export function recommendationTone(state: TodayRecommendationState): TodayDecisionTone {
  if (state === "train_as_planned") {
    return "green";
  }
  if (state === "modify") {
    return "amber";
  }
  if (state === "pull_back") {
    return "red";
  }
  return "neutral";
}

export function recommendationLabel(state: TodayRecommendationState): string {
  const labels: Record<TodayRecommendationState, string> = {
    not_checked_in: "Not checked in",
    train_as_planned: "Train as planned",
    modify: "Modify",
    pull_back: "Pull back",
  };
  return labels[state] ?? state;
}

export function injurySeverityTone(severity: InjuryFlagRecord["severity"]): TodayDecisionTone {
  if (severity === "severe") {
    return "red";
  }
  if (severity === "moderate") {
    return "amber";
  }
  return "neutral";
}

export function injuryStatusTone(status: InjuryFlagRecord["status"]): TodayDecisionTone {
  if (status === "resolved") {
    return "green";
  }
  if (status === "monitoring") {
    return "amber";
  }
  return "red";
}

export function injuryStatusLabel(status: InjuryFlagRecord["status"]): string {
  const labels: Record<InjuryFlagRecord["status"], string> = {
    open: "Open",
    monitoring: "Monitoring",
    resolved: "Resolved",
  };
  return labels[status] ?? status;
}

const CHECKIN_FLAG_LABELS: ReadonlyArray<
  [keyof TodayCheckinHistoryRecord, string]
> = [
  ["sharp_pain", "Sharp pain"],
  ["instability", "Instability"],
  ["swelling", "Swelling"],
  ["neurological_symptoms", "Neurological symptoms"],
  ["illness_symptoms", "Illness"],
  ["cannot_warm_into_movement", "Could not warm into movement"],
  ["worse_next_day_pain", "Worse next-day pain"],
];

/** The safety flags an athlete ticked on a check-in, as display labels. */
export function checkinFlagLabels(record: TodayCheckinHistoryRecord): string[] {
  return CHECKIN_FLAG_LABELS.filter(([key]) => record[key] === true).map(([, label]) => label);
}

export type HistoryChip = { label: string; tone: TodayDecisionTone };

/**
 * A check-in as quick-scan chips: sleep, body and pain, then any safety flags.
 * Only an answer that should catch the eye is coloured: amber for a warning
 * sign, red for a stop sign. ("Body sharp" means feeling sharp, a good sign.)
 */
export function checkinChips(record: TodayCheckinHistoryRecord): HistoryChip[] {
  const sleepTone: TodayDecisionTone = record.sleep === "poor" ? "amber" : "neutral";
  const bodyTone: TodayDecisionTone = record.body === "flat" ? "amber" : "neutral";
  const painTone: TodayDecisionTone =
    record.pain === "high" ? "red" : record.pain === "manageable" ? "amber" : "neutral";
  return [
    { label: `Sleep ${record.sleep}`, tone: sleepTone },
    { label: `Body ${record.body}`, tone: bodyTone },
    { label: `Pain ${record.pain}`, tone: painTone },
    ...checkinFlagLabels(record).map((label) => ({ label, tone: "red" as const })),
  ];
}

/** The injury's latest reported trend, coloured by direction. */
export function injuryReportedTone(status: InjuryFlagRecord["latest_reported_status"]): TodayDecisionTone {
  if (status === "worse") {
    return "red";
  }
  if (status === "improving" || status === "resolved") {
    return "green";
  }
  return "neutral";
}

/** True when ``day`` is one of the ``days`` training days ending ``today``. */
export function isWithinLastDays(day: string, today: string, days: number): boolean {
  const diff = trainingDaysAgo(day, today);
  return diff !== null && diff < days;
}

/** How many rows fall in the last ``days`` training days, grouped by ``key``. */
export function countRecentBy<Row, Key extends string>(
  rows: readonly Row[],
  { day, key, today, days }: { day: (row: Row) => string; key: (row: Row) => Key; today: string; days: number },
): Partial<Record<Key, number>> {
  const counts: Partial<Record<Key, number>> = {};
  for (const row of rows) {
    if (isWithinLastDays(day(row), today, days)) {
      const k = key(row);
      counts[k] = (counts[k] ?? 0) + 1;
    }
  }
  return counts;
}

// -- Sparring ----------------------------------------------------------------
// Facts, not a score: nothing here ranks or rewards contact. Heavy head
// contact is amber and a rocked/dropped report is red, matching the risk tones.

const SPARRING_INTENSITY_LABELS: Record<SparringIntensity, string> = {
  light: "Light",
  medium: "Medium",
  hard: "Hard",
};

export function sparringIntensityLabel(intensity: SparringIntensity): string {
  return SPARRING_INTENSITY_LABELS[intensity] ?? intensity;
}

export function sparringIntensityTone(intensity: SparringIntensity): TodayDecisionTone {
  return intensity === "hard" ? "amber" : "neutral";
}

export function sparringHeadContactLabel(headContact: SparringHeadContact): string {
  const labels: Record<SparringHeadContact, string> = {
    none: "No head contact",
    light: "Light head contact",
    heavy: "Heavy head contact",
  };
  return labels[headContact] ?? headContact;
}

/** "5 × 3 min", "4 × 2:30", or "5 rounds" when the length is unknown. */
export function sparringRoundsLabel(rounds: number, roundSeconds: number | null): string {
  if (!roundSeconds) {
    return `${rounds} round${rounds === 1 ? "" : "s"}`;
  }
  const minutes = Math.floor(roundSeconds / 60);
  const seconds = roundSeconds % 60;
  let length: string;
  if (minutes === 0) {
    length = `${seconds}s`;
  } else if (seconds === 0) {
    length = `${minutes} min`;
  } else {
    length = `${minutes}:${String(seconds).padStart(2, "0")}`;
  }
  return `${rounds} × ${length}`;
}

const PLANNED_LEVEL: Partial<Record<SparringPlannedIntensity, number>> = {
  technical: 0,
  light: 0,
  hard: 2,
};
const ACTUAL_LEVEL: Record<SparringIntensity, number> = { light: 0, medium: 1, hard: 2 };

/**
 * "Planned light — went hard" when the reported intensity differs from what
 * the plan called for, else null. A plain "contact" plan has no set intensity,
 * so it never differs. ``harder`` marks the overreach a coach wants to see.
 */
export function sparringPlanDifference(
  planned: SparringPlannedIntensity | null,
  actual: SparringIntensity,
): { label: string; harder: boolean } | null {
  const plannedLevel = planned ? PLANNED_LEVEL[planned] : undefined;
  if (plannedLevel === undefined || plannedLevel === ACTUAL_LEVEL[actual]) {
    return null;
  }
  return {
    label: `Planned ${planned} — went ${actual}`,
    harder: ACTUAL_LEVEL[actual] > plannedLevel,
  };
}

/** Whole training days from ``day`` to ``currentDay`` (YYYY-MM-DD), or null
 *  when either is unparseable or ``day`` is in the future. */
export function trainingDaysAgo(day: string, currentDay: string): number | null {
  const a = Date.parse(`${day.slice(0, 10)}T12:00:00Z`);
  const b = Date.parse(`${currentDay.slice(0, 10)}T12:00:00Z`);
  if (Number.isNaN(a) || Number.isNaN(b)) {
    return null;
  }
  const diff = Math.round((b - a) / 86_400_000);
  return diff < 0 ? null : diff;
}

/** "Today", "Yesterday", "N days ago" between two YYYY-MM-DD training days. */
export function daysAgoLabel(day: string, currentDay: string): string | null {
  const diff = trainingDaysAgo(day, currentDay);
  if (diff === null) {
    return null;
  }
  if (diff === 0) {
    return "Today";
  }
  if (diff === 1) {
    return "Yesterday";
  }
  return `${diff} days ago`;
}

/** Hard sparring is commonly capped at one or two days a week. */
export const HARD_SPARRING_DAYS_PER_WEEK = 2;

/**
 * A plain note when the last 7 days went past the common hard-sparring cap or
 * included a rocked/dropped report, else null. Information, not a diagnosis.
 */
export function sparringWeekNote(week: SparringWindowSummary): string | null {
  if (week.rocked_count > 0) {
    return "You logged being rocked or dropped in the last 7 days. Talk to your coach before your next hard spar.";
  }
  if (week.hard_days > HARD_SPARRING_DAYS_PER_WEEK) {
    return (
      `${week.hard_days} hard sparring days in the last 7. Most coaches cap hard sparring at ` +
      `1–${HARD_SPARRING_DAYS_PER_WEEK} days a week, with lighter days in between.`
    );
  }
  return null;
}

/** The fields a row shows under its date, in order. Heavy head contact is
 *  already a badge on the row, so it is not repeated here. */
export function sparringRowMeta(row: SparringLogRecord): string[] {
  const meta = [sparringRoundsLabel(row.rounds_completed, row.round_seconds)];
  if (row.head_contact !== "heavy") {
    meta.push(sparringHeadContactLabel(row.head_contact));
  }
  return meta;
}
