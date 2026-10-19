import type { PersonalExercise } from "./api-schema.generated";
import { detailMeasurements } from "./session-details";
import { compactTimeUnits } from "./structured-plan";

export function exerciseResult(exercise: PersonalExercise): { label: string; value: string } {
  if (exercise.best_loads.length) return {
    label: exercise.identity_kind === "legacy" ? "Recorded load" : exercise.best_loads.length > 1 ? "Best recorded loads · by unit" : "Best recorded load",
    value: exercise.best_loads.map(load => `${load.value} ${load.unit}`).join(" · "),
  };
  const values = exercise.latest_values;
  const parts: string[] = [];
  if (values.sets != null && values.reps != null) parts.push(`${values.sets} × ${values.reps}`);
  for (const item of detailMeasurements(values)) {
    if ((item.label === "Sets" || item.label === "Reps") && values.sets != null && values.reps != null) continue;
    if (item.label === "Rest" || item.label === "Effort") continue;
    parts.push(item.label === "Rounds" || item.label === "Sets" || item.label === "Reps" ? `${item.value} ${item.label.toLowerCase()}` : compactTimeUnits(item.value));
  }
  // A movement logged by name alone was performed; nothing was measured.
  const empty = exercise.latest_source === "manual" ? "No measurements recorded"
    : exercise.latest_confirmed_as_prescribed ? "Completed as prescribed" : "Modified result";
  return { label: exercise.latest_confirmed_as_prescribed ? "Latest confirmed" : "Latest recorded", value: parts.join(" · ") || empty };
}
