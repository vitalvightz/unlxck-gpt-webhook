import { isWithinLastDays } from "@/lib/history";
import type { TrainingActivity, TrainingHistorySession } from "@/lib/training-history";

/** One discipline's share of the window. Strength and conditioning are one S&C bucket. */
export type TrainingMixRow = { key: string; label: string; sessions: number; minutes: number };

export type TrainingSummary = {
  sessions: number;
  minutes: number;
  /** Counted sessions with no recorded duration: never estimated into `minutes`. */
  untimed: number;
  mix: TrainingMixRow[];
};

const DISCIPLINE: Record<TrainingActivity, { key: string; label: string }> = {
  boxing: { key: "boxing", label: "Boxing" },
  sparring: { key: "sparring", label: "Sparring" },
  strength: { key: "sc", label: "S&C" },
  conditioning: { key: "sc", label: "S&C" },
  roadwork: { key: "roadwork", label: "Roadwork" },
  other: { key: "other", label: "Other" },
};
// Prescribed sessions keep their own bucket rather than a discipline guessed from a title.
const PLAN = { key: "unlxck", label: "Unlxck plan" };

/**
 * Completed training over the last `days` athlete-local days, from records
 * already on the page. Same rows as the status counts: manual sessions and
 * reported Unlxck completions, done or modified.
 */
export function summarizeTraining(rows: readonly TrainingHistorySession[], today: string, days: number): TrainingSummary {
  const mix = new Map<string, TrainingMixRow>();
  let sessions = 0;
  let minutes = 0;
  let untimed = 0;
  for (const row of rows) {
    if (row.status === "skipped" || !isWithinLastDays(row.training_day, today, days)) continue;
    if (row.source !== "external" && row.completion_origin !== "reported") continue;
    const discipline = row.source === "external" && row.activity ? DISCIPLINE[row.activity] ?? DISCIPLINE.other : PLAN;
    const entry = mix.get(discipline.key) ?? { ...discipline, sessions: 0, minutes: 0 };
    const duration = row.duration_minutes && row.duration_minutes > 0 ? row.duration_minutes : 0;
    entry.sessions += 1;
    entry.minutes += duration;
    mix.set(discipline.key, entry);
    sessions += 1;
    minutes += duration;
    if (!duration) untimed += 1;
  }
  return {
    sessions, minutes, untimed,
    mix: [...mix.values()].sort((a, b) => b.minutes - a.minutes || b.sessions - a.sessions),
  };
}

/** "9h 15m", "45m", "2h". */
export function formatTrainingDuration(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (!hours) return `${rest}m`;
  return rest ? `${hours}h ${rest}m` : `${hours}h`;
}

/** Rows whose takeaway matches `query` (case-insensitive), newest first as given. */
export function filterTakeaways(rows: readonly TrainingHistorySession[], query: string): TrainingHistorySession[] {
  const needle = query.trim().toLowerCase();
  return rows.filter(row => row.takeaway?.trim() && (!needle || row.takeaway.toLowerCase().includes(needle)
    || row.title.toLowerCase().includes(needle)));
}
