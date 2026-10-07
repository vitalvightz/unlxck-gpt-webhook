import type { ExerciseLogRecord, ExerciseLogRequest } from "../types";
import type { TimerState } from "./engine";

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
    if (!blockId || seen.has(blockId) || existing[blockId]) {
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
    if (!planned || done >= planned.min) {
      entries.push({ block_id: blockId, status: "as_prescribed" });
      return;
    }
    entries.push({ block_id: blockId, status: "modified", actual: { [planned.field]: done } });
  });
  return entries;
}
