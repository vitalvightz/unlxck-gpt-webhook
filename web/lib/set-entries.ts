import type { ExerciseLogActual, ExerciseLogMeasure, ExerciseSetResult } from "./types";

export type SetDraft = { reps: string; load: string; rpe?: string };
export const MAX_SETS = 50;
export const blankSet = (): SetDraft => ({ reps: "", load: "" });

/** Only exact prescribed numbers are prefilled; ranges remain hints. */
export function setDrafts(count: number, reps?: number | null, load?: ExerciseLogMeasure | null): SetDraft[] {
  return Array.from({ length: Math.max(1, Math.min(MAX_SETS, count)) }, () => ({ reps: reps == null ? "" : String(reps), load: load == null ? "" : String(load.value) }));
}

export function draftsFromActual(actual: ExerciseLogActual): SetDraft[] {
  return actual.set_entries?.map(entry => ({ reps: entry.reps == null ? "" : String(entry.reps), load: entry.load == null ? "" : String(entry.load.value), ...(entry.rpe == null ? {} : { rpe: String(entry.rpe) }) }))
    ?? setDrafts(actual.sets ?? 1, actual.reps, actual.load);
}

function number(text: string): number | null {
  if (!text.trim()) return null;
  const normalized = text.trim().replace(",", ".");
  return /^\d+(?:\.\d{1,2})?$/.test(normalized) ? Number(normalized) : NaN;
}

export function readSets(rows: readonly SetDraft[], unit: string): { actual: ExerciseLogActual; invalid: number[] } {
  const invalid: number[] = [];
  const entries: ExerciseSetResult[] = rows.map((row, index) => {
    const reps = number(row.reps), load = number(row.load), rpe = number(row.rpe ?? "");
    if ((reps !== null && (!Number.isInteger(reps) || reps < 1 || reps > 1000)) ||
      (load !== null && (!Number.isFinite(load) || load < 0 || load > (unit === "lb" ? 2200 : 1000))) ||
      (rpe !== null && (!Number.isFinite(rpe) || rpe < 1 || rpe > 10 || rpe * 2 !== Math.round(rpe * 2)))) invalid.push(index);
    return { reps, load: load === null ? null : { value: load, unit }, ...(rpe === null ? {} : { rpe }) };
  });
  if (!rows.length || rows.length > MAX_SETS || !["kg", "lb"].includes(unit)) invalid.push(-1);
  return { actual: actualFromSets(entries), invalid };
}

/** Common values are compatibility summaries, never a maximum applied to every set. */
export function actualFromSets(entries: ExerciseSetResult[]): ExerciseLogActual {
  if (!entries.length) return {};
  const first = entries[0];
  return { sets: entries.length, set_entries: entries,
    reps: entries.every(entry => entry.reps === first.reps) ? first.reps : null,
    load: entries.every(entry => entry.load?.value === first.load?.value && entry.load?.unit === first.load?.unit) ? first.load : null,
    ...(entries.some(entry => entry.rpe != null) ? { effort: first.rpe != null && entries.every(entry => entry.rpe === first.rpe) ? { method: "RPE", value: first.rpe } : null } : {}) };
}

export function setSummary(entries: readonly ExerciseSetResult[]): string {
  if (!entries.length) return "";
  const reps = entries[0].reps;
  const sameReps = reps != null && entries.every(entry => entry.reps === reps);
  const parts = [sameReps ? `${entries.length} × ${reps}` : `${entries.length} ${entries.length === 1 ? "set" : "sets"}`];
  const units = [...new Set(entries.flatMap(entry => entry.load ? [entry.load.unit] : []))];
  for (const unit of units) {
    const values = entries.flatMap(entry => entry.load?.unit === unit ? [entry.load.value] : []);
    const min = Math.min(...values), max = Math.max(...values);
    parts.push(`${min === max ? min : `${min}–${max}`} ${unit}${values.length < entries.length ? ` (${values.length}/${entries.length} sets)` : ""}`);
  }
  return parts.join(" · ");
}
