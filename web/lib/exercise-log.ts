import { cleanText, finitePositiveNumber, isModeLikeReps, isTimeLikeReps } from "@/lib/structured-plan";
import type {
  ExerciseLogActual,
  ExerciseLogReason,
  ExerciseLogRecord,
  ExerciseLogStatus,
  StructuredBlock,
} from "@/lib/types";

/**
 * The model behind in-session exercise logging: which numbers an exercise can
 * be logged with, how what the athlete typed compares with the prescription,
 * and how a saved log reads back. The prescription itself is never edited.
 */

export type LogFieldKey = "sets" | "reps" | "load" | "duration" | "work" | "rounds" | "distance" | "effort";

export type LogField = {
  key: LogFieldKey;
  label: string;
  /** Unit shown beside the input ("kg", "min"); null for bare counts. */
  unit: string | null;
  /** Unit sent to the API for measured fields; null for counts and RPE. */
  apiUnit: string | null;
  /** The prescribed value, or the prescribed range ("8-12" is [8, 12]). Null
   * when the plan gives no number for this field (the weight on the bar). */
  prescribed: [number, number] | null;
  /** The prescription as written, shown as the input's placeholder. */
  hint: string | null;
};

export const EXERCISE_LOG_REASONS: readonly ExerciseLogReason[] = ["equipment", "fatigue", "pain", "felt_strong"];

export const EXERCISE_LOG_REASON_LABELS: Record<ExerciseLogReason, string> = {
  equipment: "Equipment",
  fatigue: "Fatigue",
  pain: "Pain",
  felt_strong: "Strong",
};

export const EXERCISE_LOG_STATUS_LABELS: Record<ExerciseLogStatus, string> = {
  as_prescribed: "Done",
  modified: "Changed",
  skipped: "Skipped",
};

/** A value this many times over (or under) the prescription is confirmed before saving. */
const OUTLIER_RATIO = 3;
/** With no prescribed load to compare with, anything past this is confirmed. */
const OUTLIER_LOAD_KG = 400;

// Loads the athlete cannot put a number on.
const UNWEIGHED_LOAD_METHODS = new Set(["bodyweight", "band"]);

function timeUnit(unit: unknown): { unit: string; apiUnit: string } | null {
  const text = cleanText(unit)?.toLowerCase() ?? "";
  if (/^(s|sec|secs|second|seconds)$/.test(text)) return { unit: "sec", apiUnit: "seconds" };
  if (/^(m|min|mins|minute|minutes)$/.test(text)) return { unit: "min", apiUnit: "minutes" };
  return null;
}

function distanceUnit(unit: unknown): { unit: string; apiUnit: string } | null {
  const text = cleanText(unit)?.toLowerCase() ?? "";
  if (/^(m|meter|meters|metre|metres)$/.test(text)) return { unit: "m", apiUnit: "meters" };
  if (/^(km|kilometer|kilometers|kilometre|kilometres)$/.test(text)) return { unit: "km", apiUnit: "km" };
  if (/^(mi|mile|miles)$/.test(text)) return { unit: "mi", apiUnit: "miles" };
  return null;
}

function single(value: number): [number, number] {
  return [value, value];
}

/** "8", "8-12", "5 each side" as a prescribed rep count or range; null for
 * anything that is not a rep count ("30 seconds", "AMRAP"). */
function prescribedReps(reps: StructuredBlock["reps"]): { range: [number, number]; hint: string } | null {
  if (typeof reps === "number") {
    return finitePositiveNumber(reps) ? { range: single(reps), hint: String(reps) } : null;
  }
  const text = cleanText(reps);
  if (!text || isTimeLikeReps(text) || isModeLikeReps(text)) {
    return null;
  }
  const match = /^(\d+)(?:\s*[-–—]\s*(\d+))?(?![\d.])/.exec(text);
  if (!match) {
    return null;
  }
  const low = Number(match[1]);
  const high = match[2] ? Number(match[2]) : low;
  if (!finitePositiveNumber(low) || high < low) {
    return null;
  }
  return { range: [low, high], hint: text.replace(/\s*[-–—]\s*/, "–") };
}

function measured(
  key: LogFieldKey,
  label: string,
  value: StructuredBlock["duration"],
  resolveUnit: (unit: unknown) => { unit: string; apiUnit: string } | null,
): LogField | null {
  const amount = value?.value;
  const unit = resolveUnit(value?.unit);
  if (!finitePositiveNumber(amount) || !unit) {
    return null;
  }
  return { key, label, ...unit, prescribed: single(amount), hint: String(amount) };
}

/**
 * The numbers this exercise can be logged with, in display order. A field is
 * offered when the prescription carries it; the weight used is offered for
 * rep-based work, because the plan rarely prescribes one; RPE is always offered.
 */
export function logFieldsForBlock(block: StructuredBlock): LogField[] {
  const fields: LogField[] = [];
  const sets = finitePositiveNumber(block.sets) ? block.sets : null;
  const reps = prescribedReps(block.reps);
  if (sets !== null) {
    fields.push({ key: "sets", label: "Sets", unit: null, apiUnit: null, prescribed: single(sets), hint: String(sets) });
  }
  if (reps) {
    fields.push({ key: "reps", label: "Reps", unit: null, apiUnit: null, prescribed: reps.range, hint: reps.hint });
  }
  const timed = [
    measured("duration", "Duration", block.duration, timeUnit),
    measured("work", "Work", block.work, timeUnit),
    measured("distance", "Distance", block.distance, distanceUnit),
  ].filter((field): field is LogField => field !== null);
  const loadMethod = cleanText(block.load?.method)?.toLowerCase() ?? "";
  // Sets of a sprint or a hold are not weighed; sets of reps (or bare sets) are.
  const weighed = Boolean(reps) || (sets !== null && timed.length === 0);
  if (weighed && !UNWEIGHED_LOAD_METHODS.has(loadMethod)) {
    const loadUnit = cleanText(block.load?.unit)?.toLowerCase();
    const prescribedLoad =
      (loadUnit === "kg" || loadUnit === "lb") && finitePositiveNumber(block.load?.value)
        ? block.load.value
        : null;
    fields.push({
      key: "load",
      label: "Load",
      unit: loadUnit === "lb" ? "lb" : "kg",
      apiUnit: loadUnit === "lb" ? "lb" : "kg",
      prescribed: prescribedLoad === null ? null : single(prescribedLoad),
      hint: prescribedLoad === null ? null : String(prescribedLoad),
    });
  }
  const rounds = finitePositiveNumber(block.rounds) ? block.rounds : null;
  if (rounds !== null) {
    fields.push({ key: "rounds", label: "Rounds", unit: null, apiUnit: null, prescribed: single(rounds), hint: String(rounds) });
  }
  fields.push(...timed);

  const effort = block.effort;
  const prescribedRpe =
    cleanText(effort?.method)?.toUpperCase() === "RPE" && typeof effort?.value === "number" && finitePositiveNumber(effort.value)
      ? effort.value
      : null;
  fields.push({
    key: "effort",
    label: "RPE",
    unit: null,
    apiUnit: null,
    prescribed: prescribedRpe === null ? null : single(prescribedRpe),
    hint: prescribedRpe === null ? "1–10" : String(prescribedRpe),
  });
  return fields;
}

/** Whether the exercise has anything beyond RPE to put a different number on. */
export function hasLoggableNumbers(fields: LogField[]): boolean {
  return fields.some((field) => field.key !== "effort");
}

export type LogDraft = Partial<Record<LogFieldKey, string>>;

function parseEntry(text: string | undefined): number | null {
  const cleaned = (text ?? "").trim().replace(",", ".");
  if (!/^\d+(?:\.\d+)?$/.test(cleaned)) {
    return null;
  }
  const value = Number(cleaned);
  return Number.isFinite(value) ? value : null;
}

function formatNumber(value: number): string {
  return String(Math.round(value * 100) / 100);
}

function formatPrescribed(field: LogField): string {
  if (!field.prescribed) return "";
  const [low, high] = field.prescribed;
  return low === high ? formatNumber(low) : `${formatNumber(low)}–${formatNumber(high)}`;
}

/** "3 sets", "80 kg", "15 min", "RPE 8". */
export function formatLogValue(field: LogField, value: number): string {
  const number = formatNumber(value);
  if (field.key === "effort") return `RPE ${number}`;
  if (field.unit) return `${number} ${field.unit}`;
  const noun = field.label.toLowerCase();
  return `${number} ${value === 1 ? noun.replace(/s$/, "") : noun}`;
}

function withValue(actual: ExerciseLogActual, field: LogField, value: number): void {
  switch (field.key) {
    case "sets":
    case "reps":
    case "rounds":
      actual[field.key] = value;
      break;
    case "effort":
      actual.effort = { method: "RPE", value };
      break;
    default:
      actual[field.key] = { value, unit: field.apiUnit ?? "" };
  }
}

export type LogEntryResult = {
  status: Exclude<ExerciseLogStatus, "skipped">;
  /** Only what differs from, or adds to, the prescription. */
  actual: ExerciseLogActual;
  /** Fields that could not be read as a number, or are out of range. */
  invalid: LogFieldKey[];
  /** Entries far enough from the prescription to be worth a second look. */
  outliers: string[];
};

const FIELD_LIMITS: Record<LogFieldKey, [number, number, boolean]> = {
  // [min, max, whole numbers only]
  sets: [0, 50, true],
  reps: [0, 1000, true],
  rounds: [0, 100, true],
  load: [0, 1000, false],
  duration: [0, 600, false],
  work: [0, 600, false],
  distance: [0, 100000, false],
  effort: [1, 10, false],
};

/**
 * Turn what the athlete typed into a log. An empty field means "as written".
 * A number that departs from the prescription makes the log "modified"; a
 * number the plan never gave (the weight used, the RPE felt) is recorded
 * without counting as a change.
 */
export function buildLogEntry(fields: LogField[], draft: LogDraft): LogEntryResult {
  const actual: ExerciseLogActual = {};
  const invalid: LogFieldKey[] = [];
  const outliers: string[] = [];
  let modified = false;
  for (const field of fields) {
    const text = (draft[field.key] ?? "").trim();
    if (!text) {
      continue;
    }
    const value = parseEntry(text);
    const [min, max, whole] = FIELD_LIMITS[field.key];
    if (value === null || value < min || value > max || (whole && !Number.isInteger(value))) {
      invalid.push(field.key);
      continue;
    }
    if (!field.prescribed) {
      withValue(actual, field, value);
      if (field.key === "load" && value > (field.unit === "lb" ? OUTLIER_LOAD_KG * 2.2 : OUTLIER_LOAD_KG)) {
        outliers.push(`${formatLogValue(field, value)} is a very heavy load`);
      }
      continue;
    }
    const [low, high] = field.prescribed;
    if (value >= low && value <= high) {
      // Inside a prescribed range, the exact count is still worth keeping.
      if (low !== high) {
        withValue(actual, field, value);
      }
      continue;
    }
    modified = true;
    withValue(actual, field, value);
    if (value > high * OUTLIER_RATIO || value < low / OUTLIER_RATIO) {
      outliers.push(`${formatLogValue(field, value)} against ${formatPrescribed(field)} prescribed`);
    }
  }
  return { status: modified ? "modified" : "as_prescribed", actual, invalid, outliers };
}

function actualNumber(actual: ExerciseLogActual | null | undefined, key: LogFieldKey): number | null {
  const value = key === "effort" ? actual?.effort?.value : actual?.[key];
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (value && typeof value === "object" && typeof value.value === "number") {
    return Number.isFinite(value.value) ? value.value : null;
  }
  return null;
}

/** The draft that reproduces a saved log, for editing it. */
export function draftFromLog(fields: LogField[], log: ExerciseLogRecord | null | undefined): LogDraft {
  const draft: LogDraft = {};
  for (const field of fields) {
    const value = actualNumber(log?.actual, field.key);
    if (value !== null) {
      draft[field.key] = formatNumber(value);
    }
  }
  return draft;
}

export type LoggedValue = {
  key: LogFieldKey;
  label: string;
  /** What was done, e.g. "3" or "80 kg". */
  value: string;
  /** The same with its noun: "3 sets", "80 kg", "RPE 8". */
  text: string;
  /** The prescription it replaced; null when it only adds to it. */
  insteadOf: string | null;
};

/** What a saved log recorded, field by field, for showing beside the prescription. */
export function loggedValues(fields: LogField[], log: ExerciseLogRecord): LoggedValue[] {
  const values: LoggedValue[] = [];
  for (const field of fields) {
    const value = actualNumber(log.actual, field.key);
    if (value === null) {
      continue;
    }
    const departs = Boolean(field.prescribed) && (value < field.prescribed![0] || value > field.prescribed![1]);
    const number = formatNumber(value);
    values.push({
      key: field.key,
      label: field.label,
      value: field.unit ? `${number} ${field.unit}` : number,
      text: formatLogValue(field, value),
      insteadOf: departs ? `${formatPrescribed(field)}${field.unit ? ` ${field.unit}` : ""}` : null,
    });
  }
  return values;
}

/** One line for the collapsed row: "Done", "Done · 80 kg", "Changed · 3 sets · 6 reps", "Skipped". */
export function logSummary(fields: LogField[], log: ExerciseLogRecord): string {
  const label = EXERCISE_LOG_STATUS_LABELS[log.status];
  if (log.status === "skipped") {
    return label;
  }
  const parts = fields.flatMap((field) => {
    const value = actualNumber(log.actual, field.key);
    return value === null ? [] : [formatLogValue(field, value)];
  });
  return [label, ...parts].join(" · ");
}

/** Whether a block can be logged at all: it needs its server id, and rehab is
 * logged with the session. */
export function isLoggableBlock(block: StructuredBlock): boolean {
  return Boolean(cleanText(block.block_id)) && cleanText(block.block_type) !== "rehab";
}
