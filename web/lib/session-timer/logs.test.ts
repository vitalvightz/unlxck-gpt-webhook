import test from "node:test";
import assert from "node:assert/strict";

import { createTimerState, endSession, type TimerState } from "./engine.ts";
import { timerExerciseLogs } from "./logs.ts";
import { buildTimerItems, type TimerItem } from "./plan.ts";
import type { ExerciseLogRecord, StructuredBlock } from "../types.ts";

const BLOCKS: StructuredBlock[] = [
  { block_id: "rope", block_type: "power", display_name: "Battle Rope Slams", sets: 3, reps: "8" },
  { block_id: "press", block_type: "strength", display_name: "DB Incline Press", sets: 3, reps: "8" },
  { block_id: "rdl", block_type: "strength", display_name: "Romanian Deadlift", sets: 3, reps: "8" },
  { block_id: "intervals", block_type: "conditioning", display_name: "Bike intervals", rounds: 6, work: { value: 30, unit: "seconds" } },
  { block_id: "mobility", block_type: "mobility", display_name: "Hip flow" },
];

function run(completed: number[], index: number): TimerState {
  const items: TimerItem[] = buildTimerItems([{ session_id: "s", blocks: BLOCKS }]);
  return endSession({ ...createTimerState(items), completed, index }, 0);
}

test("the plan reached is done as written, part of it is changed with the count done", () => {
  const entries = timerExerciseLogs(run([3, 2, 4, 4, 1], 4));
  assert.deepEqual(entries, [
    { block_id: "rope", status: "as_prescribed" },
    { block_id: "press", status: "modified", actual: { sets: 2 } },
    { block_id: "rdl", status: "as_prescribed" },
    { block_id: "intervals", status: "modified", actual: { rounds: 4 } },
    { block_id: "mobility", status: "as_prescribed" },
  ]);
});

test("an exercise moved past with nothing done is skipped; one never reached stays unlogged", () => {
  const entries = timerExerciseLogs(run([3, 0, 1, 0, 0], 2));
  assert.deepEqual(entries, [
    { block_id: "rope", status: "as_prescribed" },
    { block_id: "press", status: "skipped" },
    { block_id: "rdl", status: "modified", actual: { sets: 1 } },
  ]);
});

test("a block the athlete already logged by hand is never overwritten", () => {
  const existing = { press: { block_id: "press", status: "modified" } as ExerciseLogRecord };
  const entries = timerExerciseLogs(run([3, 3, 0, 0, 0], 2), existing);
  assert.deepEqual(entries.map((entry) => entry.block_id), ["rope"]);
});

test("timer items carry the plan's block id and count, not the adjusted target", () => {
  const items = buildTimerItems([{ session_id: "s", blocks: BLOCKS }]);
  assert.equal(items[1].blockId, "press");
  assert.deepEqual(items[1].planned, { field: "sets", min: 3 });
  assert.deepEqual(items[3].planned, { field: "rounds", min: 6 });
  assert.equal(items[4].planned, null);
});

test("runs saved before block ids existed log nothing", () => {
  const items = buildTimerItems([{ session_id: "s", blocks: BLOCKS }]).map(({ blockId: _drop, ...item }) => item);
  const state = endSession({ ...createTimerState(items as TimerItem[]), completed: [3, 3, 3, 6, 1], index: 4 }, 0);
  assert.deepEqual(timerExerciseLogs(state), []);
});
