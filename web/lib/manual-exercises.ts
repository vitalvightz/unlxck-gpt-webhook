import type {
  ExerciseLogActual, LibraryEntry, ManualExerciseEntry, PerformedExerciseInput, PersonalExercise,
} from "./api-schema.generated";

export type MeasurementFormat = PerformedExerciseInput["format"];
export type ExerciseChoice = PerformedExerciseInput["exercise"];
export type FieldId = "sets" | "reps" | "load" | "duration" | "rounds" | "work" | "rest" | "distance" | "effort";
type Unit = "kg" | "lb" | "seconds" | "minutes" | "meters" | "km" | "miles";

export const FORMATS: { id: MeasurementFormat; label: string }[] = [
  { id: "strength", label: "Weights" }, { id: "bodyweight", label: "Bodyweight" },
  { id: "isometric", label: "Hold" }, { id: "intervals", label: "Intervals" }, { id: "distance", label: "Distance" },
];
export const formatLabel = (format: MeasurementFormat) => FORMATS.find(item => item.id === format)!.label;

/** The first row the athlete sees for each movement. */
export const PRIMARY_FIELDS: Record<MeasurementFormat, FieldId[]> = {
  strength: ["sets", "reps", "load"], bodyweight: ["sets", "reps"], isometric: ["sets", "duration"],
  intervals: ["rounds", "work", "rest"], distance: ["distance", "duration"],
};
/** Behind "More details"; same allowlist as the API (api/contracts/manual_exercises.py). */
export const EXTRA_FIELDS: Record<MeasurementFormat, FieldId[]> = {
  strength: ["rest", "effort"], bodyweight: ["load", "rest", "effort"], isometric: ["load", "rest", "effort"],
  intervals: ["distance", "effort"], distance: ["sets", "load", "rest", "effort"],
};

export const UNIT_CHOICES: Partial<Record<FieldId, Unit[]>> = {
  load: ["kg", "lb"], duration: ["seconds", "minutes"], work: ["seconds", "minutes"], rest: ["seconds", "minutes"],
  distance: ["meters", "km", "miles"],
};
export const UNIT_LABEL: Record<Unit, string> = { kg: "kg", lb: "lb", seconds: "sec", minutes: "min", meters: "m", km: "km", miles: "mi" };

const MAX: Record<FieldId, number | Partial<Record<Unit, number>>> = {
  sets: 50, reps: 1000, rounds: 100, effort: 10,
  load: { kg: 1000, lb: 2200 }, duration: { seconds: 86400, minutes: 1440 }, work: { seconds: 3600, minutes: 60 },
  rest: { seconds: 3600, minutes: 60 }, distance: { meters: 200000, km: 200, miles: 125 },
};
const COUNTS = new Set<FieldId>(["sets", "reps", "rounds"]);

export function fieldLabel(field: FieldId, format: MeasurementFormat): string {
  if (field === "load") return format === "strength" ? "Load" : "Added load";
  if (field === "effort") return "RPE";
  if (field === "duration") return format === "isometric" ? "Hold" : "Time";
  return field.charAt(0).toUpperCase() + field.slice(1);
}

export type Draft = { values: Partial<Record<FieldId, string>>; units: Partial<Record<FieldId, Unit>>; notes: string };

export function defaultUnits(format: MeasurementFormat, preferredLoad: "kg" | "lb" = "kg"): Draft["units"] {
  return { load: preferredLoad, duration: format === "distance" ? "minutes" : "seconds", work: "seconds", rest: "seconds",
    distance: format === "intervals" ? "meters" : "km" };
}

export function blankDraft(format: MeasurementFormat, preferredLoad: "kg" | "lb" = "kg"): Draft {
  return { values: {}, units: defaultUnits(format, preferredLoad), notes: "" };
}

/** Edit an entry exactly as stored, units included. */
export function draftFromEntry(entry: Pick<ManualExerciseEntry, "format" | "actual" | "notes">): Draft {
  const draft = blankDraft(entry.format, entry.actual.load?.unit === "lb" ? "lb" : "kg");
  for (const field of Object.keys(MAX) as FieldId[]) {
    const raw = entry.actual[field];
    if (raw == null) continue;
    if (typeof raw === "number") draft.values[field] = String(raw);
    else {
      draft.values[field] = String(raw.value);
      if ("unit" in raw && raw.unit) draft.units[field] = raw.unit as Unit;
    }
  }
  draft.notes = entry.notes ?? "";
  return draft;
}

export function hasInput(draft: Draft): boolean {
  return Object.values(draft.values).some(value => value?.trim()) || Boolean(draft.notes.trim());
}

/** Only fields the athlete filled; a blank field is never 0. */
export function readDraft(format: MeasurementFormat, draft: Draft): { actual: Partial<ExerciseLogActual>; errors: Partial<Record<FieldId, string>> } {
  const actual: Record<string, unknown> = {};
  const errors: Partial<Record<FieldId, string>> = {};
  for (const field of [...PRIMARY_FIELDS[format], ...EXTRA_FIELDS[format]]) {
    const text = draft.values[field]?.trim();
    if (!text) continue;
    const value = Number(text.replace(",", "."));
    const unit = draft.units[field];
    const limit = typeof MAX[field] === "number" ? MAX[field] as number : (MAX[field] as Record<string, number>)[unit ?? ""];
    const min = field === "effort" || COUNTS.has(field) ? 1 : 0;
    if (!Number.isFinite(value)) errors[field] = "Enter a number";
    else if (COUNTS.has(field) && !Number.isInteger(value)) errors[field] = "Whole number";
    else if (value < min || (value === 0 && field !== "rest")) errors[field] = COUNTS.has(field) || field === "effort" ? `At least ${min}` : "More than 0";
    else if (value > limit) errors[field] = `Max ${limit}${unit ? ` ${UNIT_LABEL[unit]}` : ""}`;
    else if (field === "effort" && value * 2 !== Math.round(value * 2)) errors[field] = "Whole or half";
    else if (Math.round(value * 100) / 100 !== value) errors[field] = "2 decimals max";
    else actual[field] = COUNTS.has(field) ? value : field === "effort" ? { method: "RPE", value } : { value, unit };
  }
  return { actual: actual as Partial<ExerciseLogActual>, errors };
}

const time = (measure: { value: number; unit: string }) => `${measure.value} ${measure.unit === "minutes" ? "min" : "sec"}`;
const amount = (measure: { value: number; unit: string }) => `${measure.value} ${UNIT_LABEL[measure.unit as Unit] ?? measure.unit}`;

/** "3 × 5 · 80 kg". Empty when nothing was recorded; never invents a value. */
export function summarise(actual: Partial<ExerciseLogActual> | null | undefined, format?: MeasurementFormat | null): string {
  if (!actual) return "";
  const parts: string[] = [];
  const used = new Set<string>();
  if (actual.sets != null && actual.reps != null) { parts.push(`${actual.sets} × ${actual.reps}`); used.add("sets").add("reps"); }
  else if (actual.sets != null && actual.duration) { parts.push(`${actual.sets} × ${time(actual.duration)}`); used.add("sets").add("duration"); }
  if (actual.rounds != null && actual.work) { parts.push(`${actual.rounds} × ${time(actual.work)}`); used.add("rounds").add("work"); }
  if (actual.sets != null && !used.has("sets")) parts.push(`${actual.sets} ${actual.sets === 1 ? "set" : "sets"}`);
  if (actual.reps != null && !used.has("reps")) parts.push(`${actual.reps} reps`);
  if (actual.rounds != null && !used.has("rounds")) parts.push(`${actual.rounds} rounds`);
  if (actual.distance) parts.push(amount(actual.distance));
  if (actual.duration && !used.has("duration")) parts.push(time(actual.duration));
  if (actual.work && !used.has("work")) parts.push(`${time(actual.work)} work`);
  if (actual.load) parts.push(`${format && format !== "strength" && format !== "distance" ? "+" : ""}${amount(actual.load)}`);
  if (actual.rest) parts.push(`${time(actual.rest)} rest`);
  if (actual.effort) parts.push(`RPE ${actual.effort.value}`);
  return parts.join(" · ");
}

export const NO_MEASUREMENTS = "Performed · no measurements recorded";

export type ExerciseOption =
  | { kind: "recorded"; exercise: PersonalExercise }
  | { kind: "catalogue"; entry: LibraryEntry }
  | { kind: "new"; name: string };

export const normaliseName = (name: string) => name.trim().replace(/\s+/g, " ");
const nameKey = (name: string) => normaliseName(name).toLocaleLowerCase();

export function optionName(option: ExerciseOption): string {
  return option.kind === "recorded" ? option.exercise.name : option.kind === "catalogue" ? option.entry.name : normaliseName(option.name);
}

export function optionChoice(option: ExerciseOption): ExerciseChoice {
  if (option.kind === "catalogue") return { catalogue_id: option.entry.catalogue_id };
  if (option.kind === "new") return { name: normaliseName(option.name) };
  const { id } = option.exercise;
  return id.startsWith("custom:") ? { personal_exercise_id: id.slice(7) } : { exercise_key: id.slice(4) };
}

/** The athlete's own last layout, then the catalogue's evidence; null asks. */
export function optionFormat(option: ExerciseOption): MeasurementFormat | null {
  return option.kind === "recorded" ? option.exercise.log_format ?? null : option.kind === "catalogue" ? option.entry.log_format ?? null : null;
}

/** Stable identities only: unkeyed legacy records cannot be logged against. */
export function recordedOptions(exercises: readonly PersonalExercise[], query: string, limit = 5): PersonalExercise[] {
  const q = nameKey(query);
  const eligible = exercises.filter(item => item.identity_kind !== "legacy");
  const byRecent = (a: PersonalExercise, b: PersonalExercise) => b.latest_day.localeCompare(a.latest_day) || a.name.localeCompare(b.name);
  if (!q) return [...eligible].sort(byRecent).slice(0, limit);
  const starts = eligible.filter(item => nameKey(item.name).startsWith(q)).sort(byRecent);
  const contains = eligible.filter(item => !nameKey(item.name).startsWith(q) && nameKey(item.name).includes(q)).sort(byRecent);
  return [...starts, ...contains].slice(0, limit);
}

/** Recorded first, then catalogue matches not already recorded, then a new name unless it already exists. */
export function searchOptions(recorded: readonly PersonalExercise[], catalogue: readonly LibraryEntry[], query: string): ExerciseOption[] {
  const mine = recordedOptions(recorded, query);
  const keys = new Set(recorded.map(item => item.id));
  const library = catalogue.filter(entry => entry.category === "training" && entry.exercise_key && !keys.has(`key:${entry.exercise_key}`)).slice(0, 6);
  const options: ExerciseOption[] = [...mine.map(exercise => ({ kind: "recorded" as const, exercise })), ...library.map(entry => ({ kind: "catalogue" as const, entry }))];
  const typed = normaliseName(query);
  if (typed && !options.some(option => nameKey(optionName(option)) === nameKey(typed)) && !recorded.some(item => nameKey(item.name) === nameKey(typed))) {
    options.push({ kind: "new", name: typed.slice(0, 100) });
  }
  return options;
}
