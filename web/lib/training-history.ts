export const TRAINING_ACTIVITIES = ["sparring", "boxing", "roadwork", "strength", "conditioning", "other"] as const;
export const TRAINING_EFFORTS = ["easy", "moderate", "hard"] as const;
export type TrainingActivity = (typeof TRAINING_ACTIVITIES)[number];
export type TrainingEffort = (typeof TRAINING_EFFORTS)[number];
export type ExternalTrainingFields = {
  activity: TrainingActivity;
  duration_minutes: number;
  effort: TrainingEffort;
};
export type TrainingHistorySession = {
  id: string;
  source: "unlxck" | "external";
  training_day: string;
  status: "done" | "modified" | "skipped";
  title: string;
  activity: TrainingActivity | null;
  duration_minutes: number | null;
  effort: TrainingEffort | null;
  plan_id: string | null;
  session_rpe?: number | null;
  pain_after?: number | null;
  modification_reason?: string | null;
  notes?: string | null;
};

export function sortTrainingHistory(rows: TrainingHistorySession[]): TrainingHistorySession[] {
  return [...rows].sort((a, b) => b.training_day.localeCompare(a.training_day));
}
