// Pure display helpers for the /history page (Sessions / Check-ins /
// Injuries). Kept free of React so the tone and label mapping is unit-testable
// with node:test.

import type { TodayDecisionTone } from "@/lib/today";
import type {
  InjuryFlagRecord,
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
