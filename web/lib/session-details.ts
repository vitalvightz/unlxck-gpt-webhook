import { formatBlockLoad, formatMeasured } from "./structured-plan";
import type { LoadPrescription, MeasuredValue } from "./types";
import type { ExerciseSetResult } from "./types";
import { setSummary } from "./set-entries";

const LABELS: Record<string, string> = {
  sets: "Sets", reps: "Reps", rounds: "Rounds", load: "Load", work: "Work", rest: "Rest",
  duration: "Duration", distance: "Distance", effort: "Effort", tempo: "Tempo", intensity: "Intensity",
  prescription_text: "Dose", duration_seconds: "Duration", hold_seconds: "Hold",
  external_load_kg: "Load", distance_metres: "Distance", completed_fraction: "Completed",
};

/** Format only stored fields, preserving their own units. Never fill actuals from prescriptions. */
export function detailMeasurements(values: Record<string, unknown>): { label: string; value: string }[] {
  const sets = Array.isArray(values.set_entries) && values.set_entries.length ? values.set_entries as ExerciseSetResult[] : null;
  return [...(sets ? [{ label: "Sets", value: setSummary(sets) }] : []), ...Object.entries(LABELS).flatMap(([key, label]) => {
    if (sets && ["sets", "reps", "load"].includes(key)) return [];
    const raw = values[key];
    if (raw == null || raw === "") return [];
    let value: string | null = null;
    if (typeof raw === "object" && !Array.isArray(raw)) {
      const measure = raw as Record<string, unknown>;
      if (key === "load") value = formatBlockLoad(raw as LoadPrescription);
      if (!value && key === "effort" && typeof measure.value === "number") value = `${measure.method || "RPE"} ${measure.value}`;
      if (!value) value = formatMeasured(raw as MeasuredValue);
    } else if (typeof raw === "string" || (typeof raw === "number" && Number.isFinite(raw))) {
      value = String(raw);
      if (key.endsWith("_seconds")) value += " sec";
      if (key === "external_load_kg") value += " kg";
      if (key === "distance_metres") value += " m";
      if (key === "completed_fraction" && typeof raw === "number") value = `${Math.round(raw * 100)}%`;
    }
    return value ? [{ label, value }] : [];
  })];
}
