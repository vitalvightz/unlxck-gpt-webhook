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

/** "sleep good · body normal · pain none" style one-liner for a check-in row. */
export function checkinSummary(record: TodayCheckinHistoryRecord): string {
  return [
    `Sleep ${record.sleep}`,
    `Body ${record.body}`,
    `Pain ${record.pain}`,
  ].join(" · ");
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

/** "Today", "Yesterday", "N days ago" between two YYYY-MM-DD training days. */
export function daysAgoLabel(day: string, currentDay: string): string | null {
  const a = Date.parse(`${day.slice(0, 10)}T12:00:00Z`);
  const b = Date.parse(`${currentDay.slice(0, 10)}T12:00:00Z`);
  if (Number.isNaN(a) || Number.isNaN(b)) {
    return null;
  }
  const diff = Math.round((b - a) / 86_400_000);
  if (diff < 0) {
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
