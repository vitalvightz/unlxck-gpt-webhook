import { compactTimeUnits, formatBlockLoad, formatMeasured } from "./structured-plan";
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
  return [...(sets ? [{ label: "Sets", value: setSummary(sets, typeof values.sets === "number" ? values.sets : undefined) }] : []), ...Object.entries(LABELS).flatMap(([key, label]) => {
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

/** One line for a collapsed record: "3 × 180s · rest 60s", "2 × 3 · 25–30 kg". Effort stays in the full record. */
export function measurementSummary(values: Record<string, unknown>): string {
  if (typeof values.prescription_text === "string" && values.prescription_text.trim()) return values.prescription_text.trim();
  const items = detailMeasurements(values);
  const value = (label: string) => items.find(item => item.label === label)?.value;
  const parts: string[] = [];
  const used = new Set(["Dose", "Effort"]);
  if (!Array.isArray(values.set_entries) && value("Sets") && value("Reps")) { parts.push(`${value("Sets")} × ${value("Reps")}`); used.add("Sets").add("Reps"); }
  if (value("Rounds") && value("Work")) { parts.push(`${value("Rounds")} × ${compactTimeUnits(value("Work")!)}`); used.add("Rounds").add("Work"); }
  for (const item of items) {
    if (used.has(item.label)) continue;
    if (item.label === "Rest") parts.push(`rest ${compactTimeUnits(item.value)}`);
    else if (["Rounds", "Reps"].includes(item.label) || (item.label === "Sets" && !Array.isArray(values.set_entries))) parts.push(`${item.value} ${item.label.toLowerCase()}`);
    else parts.push(compactTimeUnits(item.value));
  }
  return parts.join(" · ");
}

/** True when every reported value repeats the prescription, so showing both adds nothing. */
export function matchesPrescription(prescribed: Record<string, unknown>, actual: Record<string, unknown>): boolean {
  const entries = Array.isArray(actual.set_entries) ? actual.set_entries as ExerciseSetResult[] : null;
  if (entries?.length) {
    if (entries.some(entry => entry.load != null || entry.rpe != null)) return false;
    const reps = entries[0].reps;
    if (reps == null || entries.some(entry => entry.reps !== reps)) return false;
    if (String(prescribed.reps) !== String(reps) || prescribed.sets !== (actual.sets ?? entries.length)) return false;
    actual = Object.fromEntries(Object.entries(actual).filter(([key]) => !["set_entries", "sets", "reps"].includes(key)));
  }
  const given = detailMeasurements(actual);
  if (!given.length) return !!entries?.length;
  const expected = new Map(detailMeasurements(prescribed).map(item => [item.label, item.value]));
  return given.every(item => expected.get(item.label) === item.value);
}
