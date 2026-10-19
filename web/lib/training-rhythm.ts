import type { TrainingHistorySession } from "./training-history";
import { trainingDaysAgo } from "./history";
import { isRecordedTraining, trainingDiscipline } from "./training-summary";

// Calendar arithmetic on stored local dates, independent of the browser's timezone/DST.
export function shiftTrainingDay(day: string, days: number): string {
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function weekStart(day: string): string {
  return shiftTrainingDay(day, -((new Date(`${day}T12:00:00Z`).getUTCDay() + 6) % 7));
}

export function rhythmWindowDays(today: string, weeks: number): number {
  return trainingDaysAgo(shiftTrainingDay(weekStart(today), -(weeks - 1) * 7), today)! + 1;
}

export type TrainingWeek = {
  start: string; end: string; current: boolean;
  rows: TrainingHistorySession[]; sessions: number; minutes: number; untimed: number;
};

export function trainingWeeks(rows: readonly TrainingHistorySession[], today: string, weeks: number, discipline = "all"): TrainingWeek[] {
  const current = weekStart(today);
  const buckets: TrainingWeek[] = Array.from({ length: weeks }, (_, index) => {
    const start = shiftTrainingDay(current, (index - weeks + 1) * 7);
    return { start, end: shiftTrainingDay(start, 6), current: start === current, rows: [], sessions: 0, minutes: 0, untimed: 0 };
  });
  const byStart = new Map(buckets.map(week => [week.start, week]));
  const seen = new Set<string>();
  for (const row of rows) {
    if (!isRecordedTraining(row) || trainingDaysAgo(row.training_day, today) === null || row.training_day > today) continue;
    if (discipline !== "all" && trainingDiscipline(row).key !== discipline) continue;
    const key = `${row.source}:${row.id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const week = byStart.get(weekStart(row.training_day));
    if (!week) continue;
    week.rows.push(row);
    week.sessions++;
    const minutes = row.duration_minutes;
    if (typeof minutes === "number" && Number.isFinite(minutes) && minutes > 0) week.minutes += minutes;
    else week.untimed++;
  }
  return buckets;
}

export function weekValue(week: TrainingWeek, metric: "sessions" | "minutes"): number | null {
  return metric === "sessions" ? week.sessions : week.sessions > 0 && week.sessions === week.untimed ? null : week.minutes;
}

export function weekComparison(weeks: TrainingWeek[], metric: "sessions" | "minutes"): string {
  const complete = weeks.filter(week => !week.current);
  const latest = complete.at(-1), previous = complete.at(-2);
  if (!latest || !previous) return "";
  // Zero against zero is not "no change" when the only training in either week lacks a duration.
  if (metric === "minutes" && !latest.minutes && !previous.minutes && (latest.untimed || previous.untimed))
    return "Training time comparison unavailable. Neither week has recorded durations.";
  const difference = latest[metric] - previous[metric];
  const change = difference === 0 ? "No change in" : `${difference > 0 ? "+" : "−"}${Math.abs(difference)} `;
  const label = metric === "minutes" ? "recorded minutes" : Math.abs(difference) === 1 ? "session" : "sessions";
  const missing = metric === "minutes" && (latest.untimed || previous.untimed)
    ? ` Missing durations: ${latest.untimed} last completed week; ${previous.untimed} previous week.` : "";
  return `${change}${difference === 0 ? " " : ""}${label} versus the previous week.${missing}`;
}
