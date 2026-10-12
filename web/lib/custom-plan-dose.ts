import type { CustomDose } from "./api-schema.generated";
export const blankDose = (mode: CustomDose["mode"] = "reps"): CustomDose => ({
  mode,
  sets: null,
  reps: null,
  duration_seconds: null,
  rest_seconds: null,
  load_or_intensity: null,
  rounds: null,
  work_seconds: null,
  rpe: null,
  tempo: null,
  per_side: null,
  distance: null,
  distance_unit: null,
  prescription: null,
});
export function doseSummary(d: CustomDose) {
  const parts = [
    d.mode === "reps"
      ? d.sets && d.reps
        ? `${d.sets} × ${d.reps}`
        : "Set dose"
      : d.mode === "duration"
        ? d.duration_seconds
          ? `${d.duration_seconds / 60} min`
          : "Set duration"
        : d.mode === "intervals"
          ? d.rounds && d.work_seconds
            ? `${d.rounds} × ${d.work_seconds / 60} min`
            : "Set intervals"
          : d.prescription || "Set prescription",
  ];
  if (d.distance) parts.push(`${d.distance} ${d.distance_unit ?? ""}`);
  if (d.load_or_intensity) parts.push(d.load_or_intensity);
  if (d.rest_seconds != null) parts.push(`rest ${d.rest_seconds}s`);
  if (d.rpe) parts.push(`RPE ${d.rpe}`);
  if (d.per_side) parts.push("per side");
  return parts.join(" · ");
}

export function doseIncomplete(d: CustomDose): boolean {
  if (d.mode === "reps") return !(d.sets && d.reps);
  if (d.mode === "duration") return !d.duration_seconds || Boolean(d.distance) !== Boolean(d.distance_unit);
  if (d.mode === "intervals") return !(d.rounds && d.work_seconds) || d.rest_seconds == null;
  return !d.prescription?.trim();
}
