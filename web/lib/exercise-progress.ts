import type { ExercisePerformance } from "./api-schema.generated";

export const PROGRESS_METRICS = [
  { key: "load", label: "Load" }, { key: "reps", label: "Reps" },
  { key: "duration", label: "Duration" }, { key: "work", label: "Work duration" },
  { key: "distance", label: "Distance" }, { key: "rounds", label: "Rounds" },
] as const;
export type ProgressMetric = typeof PROGRESS_METRICS[number]["key"];
export type ProgressSeries = { id: string; metric: ProgressMetric; label: string; unit: string };

/** Only the server's eligible performed projection supplies chart evidence. */
export function performanceValue(record: ExercisePerformance, metric: ProgressMetric): { value: number; unit: string } | null {
  const raw = record.performed_values?.[metric];
  if (raw == null) return null;
  const value = typeof raw === "number" ? raw : raw.value;
  const unit = typeof raw === "number" ? metric : raw.unit;
  return Number.isFinite(value) && value > 0 ? { value, unit } : null;
}

export function progressSeries(records: readonly ExercisePerformance[]): ProgressSeries[] {
  const result: ProgressSeries[] = [];
  for (const metric of PROGRESS_METRICS) {
    const units = new Set<string>();
    // Latest available unit first, independent of page order.
    for (const record of [...records].sort((a, b) => b.training_day.localeCompare(a.training_day) || b.id.localeCompare(a.id))) {
      const value = performanceValue(record, metric.key);
      if (value && !units.has(value.unit)) {
        units.add(value.unit);
        result.push({ id: `${metric.key}:${value.unit}`, metric: metric.key, label: metric.label, unit: value.unit });
      }
    }
  }
  return result;
}

export function progressPoints(records: readonly ExercisePerformance[], series: ProgressSeries) {
  return [...records].sort((a, b) => a.training_day.localeCompare(b.training_day) || a.id.localeCompare(b.id)).map(record => {
    const value = performanceValue(record, series.metric);
    return { record, value: value?.unit === series.unit ? value.value : null };
  });
}
