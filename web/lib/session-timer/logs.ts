import type { ExerciseLogRecord, ExerciseLogRequest } from "../types";
import type { TimerState } from "./engine";
import { buildSetLogEntry } from "../exercise-log";
import { actualFromSets, readSets } from "../set-entries";

export type TimerLogEntry = Omit<ExerciseLogRequest, "plan_id">;

/**
 * What the timer recorded, as exercise logs, so the athlete never re-ticks work
 * the timer already counted:
 * - the planned count reached (or no count to compare against) → done as written;
 * - part of it → changed, carrying the sets / rounds actually done;
 * - nothing, on an exercise the athlete moved past → skipped.
 *
 * An exercise the run never got to stays unlogged, and so does any block the
 * athlete already logged by hand: those numbers (the weight on the bar) are
 * theirs and are never overwritten.
 */
export function timerExerciseLogs(
  state: TimerState,
  existing: Readonly<Record<string, ExerciseLogRecord>> = {},
): TimerLogEntry[] {
  const entries: TimerLogEntry[] = [];
  const seen = new Set<string>();
  state.items.forEach((item, index) => {
    const blockId = item.blockId;
    // Rehab evidence belongs to session completion, never the exercise-log
    // endpoint. One rehab entry would reject the entire atomic exercise batch.
    if (item.blockType?.trim() === "rehab" || !blockId || seen.has(blockId) || existing[blockId]) {
      return;
    }
    seen.add(blockId);
    const done = state.completed[index] ?? 0;
    if (done === 0) {
      if (index < state.index) {
        entries.push({ block_id: blockId, status: "skipped" });
      }
      return;
    }
    const planned = item.planned ?? null;
    if (item.kind === "sets" && item.setFields && state.setDrafts?.[item.id]) {
      const unit = item.setFields.find(field => field.key === "load")?.apiUnit ?? "kg";
      const reported = state.setDrafts[item.id].slice(0, done).flatMap((row, at) => {
        if (!state.confirmedSetLogs?.[item.id]?.includes(at + 1)) return [];
        const read = readSets([row], unit);
        if (read.invalid.length || !read.actual.set_entries?.length) return [];
        return [{ row, entry: { ...read.actual.set_entries[0], set_number: at + 1 } }];
      });
      const result = reported.length ? buildSetLogEntry(item.setFields, reported.map(({ row }) => row), unit) : null;
      entries.push({ block_id: blockId,
        status: reported.length === done && result ? result.status : "modified",
        actual: actualFromSets(reported.map(({ entry }) => entry), done),
      });
      return;
    }
    if (!planned || done >= planned.min) {
      entries.push({ block_id: blockId, status: "as_prescribed" });
      return;
    }
    entries.push({ block_id: blockId, status: "modified", actual: { [planned.field]: done } });
  });
  return entries;
}
