import test from "node:test";
import assert from "node:assert/strict";

import {
  buildLogEntry,
  draftFromLog,
  hasLoggableNumbers,
  isLoggableBlock,
  logFieldsForBlock,
  logSummary,
  loggedValues,
} from "./exercise-log";
import type { ExerciseLogRecord, StructuredBlock } from "@/lib/types";

const deadlift: StructuredBlock = {
  block_id: "blk-2026-10-12-trap-bar-deadlift",
  block_type: "strength",
  display_name: "Trap Bar Deadlift",
  sets: 4,
  reps: 8,
  effort: { method: "RPE", value: 7 },
  rest: { value: 120, unit: "seconds" },
};

const plank: StructuredBlock = {
  block_id: "blk-2026-10-12-front-plank",
  block_type: "accessory",
  display_name: "Front Plank",
  duration: { value: 3, unit: "minutes" },
};

function log(block: StructuredBlock, overrides: Partial<ExerciseLogRecord>): ExerciseLogRecord {
  return {
    id: "log-1",
    athlete_id: "athlete-1",
    plan_id: "plan-1",
    session_id: "s1",
    block_id: block.block_id ?? "",
    exercise_key: null,
    training_day: "2026-10-12",
    status: "as_prescribed",
    reason: null,
    prescribed: block,
    actual: {},
    notes: "",
    created_at: "",
    updated_at: "",
    ...overrides,
  };
}

const keys = (block: StructuredBlock) => logFieldsForBlock(block).map((field) => field.key);

test("a lift is logged with sets, reps, the weight used and RPE", () => {
  assert.deepEqual(keys(deadlift), ["sets", "reps", "load", "effort"]);
  const load = logFieldsForBlock(deadlift).find((field) => field.key === "load");
  // The plan gives no absolute load, so there is nothing to compare it with.
  assert.equal(load?.prescribed, null);
  assert.equal(load?.unit, "kg");
});

test("every load type offers its own fields", () => {
  assert.deepEqual(keys(plank), ["duration", "effort"]);
  assert.deepEqual(
    keys({ block_type: "conditioning", rounds: 6, work: { value: 30, unit: "seconds" }, rest: { value: 30, unit: "seconds" } }),
    ["rounds", "work", "effort"],
  );
  // Sets of a sprint are not weighed; bare sets (a sled push) are.
  assert.deepEqual(keys({ block_type: "speed", sets: 4, distance: { value: 20, unit: "meters" } }), [
    "sets",
    "distance",
    "effort",
  ]);
  assert.deepEqual(keys({ block_type: "strength", sets: 3 }), ["sets", "load", "effort"]);
  // A bodyweight or band exercise has no weight to enter.
  assert.deepEqual(keys({ sets: 3, reps: 12, load: { method: "bodyweight", unit: "bodyweight" } }), [
    "sets",
    "reps",
    "effort",
  ]);
  // Nothing measurable: only how it felt.
  assert.deepEqual(keys({ block_type: "skill", display_name: "Shadow rounds" }), ["effort"]);
  assert.equal(hasLoggableNumbers(logFieldsForBlock({ display_name: "Shadow rounds" })), false);
});

test("reps written as a range, with a side note or as time are read correctly", () => {
  const reps = (value: StructuredBlock["reps"]) =>
    logFieldsForBlock({ sets: 3, reps: value }).find((field) => field.key === "reps");
  assert.deepEqual(reps("8-12")?.prescribed, [8, 12]);
  assert.equal(reps("8-12")?.hint, "8–12");
  assert.deepEqual(reps("5 each side")?.prescribed, [5, 5]);
  assert.equal(reps("30 seconds"), undefined);
  assert.equal(reps("AMRAP"), undefined);
  assert.equal(reps(0), undefined);
});

test("a free-text unit the API cannot store is not offered", () => {
  assert.deepEqual(keys({ duration: { value: 20, unit: "sec_per_side" } }), ["effort"]);
});

test("an empty entry is the exercise done as written", () => {
  assert.deepEqual(buildLogEntry(logFieldsForBlock(deadlift), {}), {
    status: "as_prescribed",
    actual: {},
    invalid: [],
    outliers: [],
  });
});

test("only what departs from the prescription is recorded, and it marks the log modified", () => {
  const entry = buildLogEntry(logFieldsForBlock(deadlift), { sets: "3", reps: "8", load: "80" });
  assert.equal(entry.status, "modified");
  assert.deepEqual(entry.actual, { sets: 3, load: { value: 80, unit: "kg" } });
  assert.deepEqual(entry.outliers, []);
});

test("the weight used and the RPE felt add to a log without making it a change", () => {
  const entry = buildLogEntry(logFieldsForBlock(deadlift), { load: "92,5", effort: "7" });
  assert.equal(entry.status, "as_prescribed");
  assert.deepEqual(entry.actual, { load: { value: 92.5, unit: "kg" } });
  // A different RPE from the one prescribed is a change.
  assert.equal(buildLogEntry(logFieldsForBlock(deadlift), { effort: "9" }).status, "modified");
});

test("a count inside a prescribed range is kept but is not a change", () => {
  const fields = logFieldsForBlock({ sets: 3, reps: "8-12" });
  assert.deepEqual(buildLogEntry(fields, { reps: "10" }), {
    status: "as_prescribed",
    actual: { reps: 10 },
    invalid: [],
    outliers: [],
  });
  assert.equal(buildLogEntry(fields, { reps: "6" }).status, "modified");
});

test("an entry far from the prescription is flagged for confirmation", () => {
  const far = buildLogEntry(logFieldsForBlock(plank), { duration: "15" });
  assert.equal(far.status, "modified");
  assert.deepEqual(far.actual, { duration: { value: 15, unit: "minutes" } });
  assert.deepEqual(far.outliers, ["15 min against 3 prescribed"]);
  // A modest change is saved without a second question.
  assert.deepEqual(buildLogEntry(logFieldsForBlock(plank), { duration: "4" }).outliers, []);
  assert.deepEqual(buildLogEntry(logFieldsForBlock(deadlift), { sets: "1" }).outliers, ["1 set against 4 prescribed"]);
  assert.deepEqual(buildLogEntry(logFieldsForBlock(deadlift), { load: "800" }).outliers, ["800 kg is a very heavy load"]);
});

test("entries that are not usable numbers are reported, not sent", () => {
  const entry = buildLogEntry(logFieldsForBlock(deadlift), { sets: "2.5", reps: "ten", load: "-5", effort: "11" });
  assert.deepEqual(entry.invalid, ["sets", "reps", "load", "effort"]);
  assert.deepEqual(entry.actual, {});
});

test("a saved log reads back as its draft, its values and its one-line summary", () => {
  const fields = logFieldsForBlock(deadlift);
  const changed = log(deadlift, {
    status: "modified",
    reason: "equipment",
    actual: { sets: 3, reps: 6, load: { value: 80, unit: "kg" } },
  });
  assert.deepEqual(draftFromLog(fields, changed), { sets: "3", reps: "6", load: "80" });
  assert.deepEqual(loggedValues(fields, changed), [
    { key: "sets", label: "Sets", value: "3", text: "3 sets", insteadOf: "4" },
    { key: "reps", label: "Reps", value: "6", text: "6 reps", insteadOf: "8" },
    { key: "load", label: "Load", value: "80 kg", text: "80 kg", insteadOf: null },
  ]);
  assert.equal(logSummary(fields, changed), "Changed · 3 sets · 6 reps · 80 kg");
  assert.equal(logSummary(fields, log(deadlift, {})), "Done");
  assert.equal(logSummary(fields, log(deadlift, { actual: { load: { value: 100, unit: "kg" } } })), "Done · 100 kg");
  assert.equal(logSummary(fields, log(deadlift, { status: "skipped", reason: "pain" })), "Skipped");
  assert.equal(
    logSummary(logFieldsForBlock(plank), log(plank, { status: "modified", actual: { duration: { value: 15, unit: "minutes" } } })),
    "Changed · 15 min",
  );
});

test("only blocks with a server id are loggable, and rehab never is", () => {
  assert.equal(isLoggableBlock(deadlift), true);
  assert.equal(isLoggableBlock({ ...deadlift, block_id: null }), false);
  assert.equal(isLoggableBlock({ ...deadlift, block_id: "  " }), false);
  assert.equal(isLoggableBlock({ block_id: "rehab:1", block_type: "rehab" }), false);
});
