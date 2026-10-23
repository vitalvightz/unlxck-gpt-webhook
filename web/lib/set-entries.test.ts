import test from "node:test";
import assert from "node:assert/strict";
import { actualFromSets, draftsFromActual, readSets, setDrafts, setSummary } from "./set-entries";
import { buildSetLogEntry, logFieldsForBlock, setDraftsForFields } from "./exercise-log";
import { buildTimerItems } from "./session-timer/plan";
import { createTimerState, startItem, skipRest, advance } from "./session-timer/engine";
import { completeSetWithResults, timerSetDrafts, endSessionWithResults, confirmSetLog, confirmAllSetLogs, unconfirmedSets } from "./session-timer/sets";
import { timerExerciseLogs } from "./session-timer/logs";

const block = { block_id: "press", display_name: "Bench Press", block_type: "strength", sets: 3, reps: 8, load: { method: "absolute", value: 25, unit: "kg" } };

test("exact prescriptions prefill every set without sharing mutable rows", () => {
  const rows = setDraftsForFields(logFieldsForBlock(block));
  assert.deepEqual(rows, setDrafts(3, 8, { value: 25, unit: "kg" }));
  rows[1].load = "27.5";
  assert.equal(rows[0].load, "25"); assert.equal(rows[2].load, "25");
  const result = buildSetLogEntry(logFieldsForBlock(block), rows, "kg");
  assert.equal(result.status, "modified");
  assert.equal(result.actual.load, null);
  assert.deepEqual(result.actual.set_entries?.map(entry => entry.load?.value), [25, 27.5, 25]);
  assert.equal(setSummary(result.actual.set_entries!), "3 × 8 · 25–27.5 kg");
});

test("unknowns stay blank and invalid input never becomes zero", () => {
  assert.equal(readSets([{ reps: "", load: "" }], "kg").actual.set_entries?.[0].load, null);
  for (const row of [{ reps: "8.5", load: "25" }, { reps: "8", load: "abc" }, { reps: "8", load: "-1" }]) {
    assert.deepEqual(readSets([row], "kg").invalid, [0]);
  }
  const range = setDraftsForFields(logFieldsForBlock({ ...block, reps: "8–12" }));
  assert.ok(range.every(row => row.reps === ""));
  assert.equal(setSummary([{ reps: 8, load: { value: 25, unit: "kg" } }, { reps: 8, load: null }]), "2 × 8 · 25 kg (1/2 sets)");
});

test("saved varied sets reopen without flattening them", () => {
  const actual = actualFromSets([{ reps: 8, load: { value: 25, unit: "kg" } }, { reps: 6, load: { value: 30, unit: "kg" } }]);
  assert.equal(actual.reps, null); assert.equal(actual.load, null);
  assert.deepEqual(draftsFromActual(actual), [{ reps: "8", load: "25" }, { reps: "6", load: "30" }]);
});

test("timer records only confirmed sets and keeps edits through JSON resume", () => {
  const items = buildTimerItems([{ blocks: [block] }]);
  let state = startItem(createTimerState(items), 0).state;
  const rows = timerSetDrafts(state)!;
  rows[0].load = "27.5";
  rows[1].load = "30";
  state = { ...state, setDrafts: { press: rows } };
  state = completeSetWithResults(state, 1000).state;
  assert.equal(state.phase, "rest"); assert.equal(state.completed[0], 1);
  assert.equal(timerExerciseLogs(state)[0].actual?.set_entries?.[0].load, null);
  state = confirmSetLog(state, "press", 1);
  const restored = JSON.parse(JSON.stringify(state));
  const logs = timerExerciseLogs(restored);
  assert.equal(logs[0].status, "modified");
  assert.equal(logs[0].actual?.sets, 1);
  assert.deepEqual(logs[0].actual?.set_entries?.map(entry => entry.load?.value), [27.5]);
  state = skipRest(state, 2000).state;
  state = completeSetWithResults(state, 3000).state;
  state = confirmSetLog(state, "press", 2);
  assert.deepEqual(timerExerciseLogs(state)[0].actual?.set_entries?.map(entry => entry.load?.value), [27.5, 30]);
});

test("invalid drafts never block rest or reset its clock, and cannot be confirmed", () => {
  const items = buildTimerItems([{ blocks: [block] }]);
  let state = startItem(createTimerState(items), 0).state;
  const rows = timerSetDrafts(state)!;
  rows[0].reps = "bad";
  rows[1].load = "bad";
  state = completeSetWithResults({ ...state, setDrafts: { press: rows } }, 1000).state;
  assert.equal(state.phase, "rest"); assert.equal(state.completed[0], 1);
  assert.equal(confirmSetLog(state, "press", 1), state);
  rows[0].reps = "8"; rows[0].rpe = "8.5";
  const confirmed = confirmSetLog(state, "press", 1);
  assert.equal(confirmed.phaseStartedAt, state.phaseStartedAt);
  assert.equal(confirmed.phaseMs, state.phaseMs);
  assert.equal(confirmed.pausedAt, null);
  assert.deepEqual(unconfirmedSets(confirmed), []);
  assert.equal(timerExerciseLogs(confirmed)[0].actual?.set_entries?.[0].rpe, 8.5);
});

test("end review retains missed and invalid entries until corrected and confirmed", () => {
  let state = startItem(createTimerState(buildTimerItems([{ blocks: [block] }])), 0).state;
  state = completeSetWithResults(state, 1000).state;
  state.setDrafts!.press[0].load = "invalid";
  state = endSessionWithResults(state, 2000);
  assert.equal(state.phase, "done");
  assert.deepEqual(unconfirmedSets(confirmAllSetLogs(state)), [{ itemId: "press", set: 1 }]);
  state.setDrafts!.press[0].load = "27.5";
  const reviewed = confirmAllSetLogs(state);
  assert.deepEqual(unconfirmedSets(reviewed), []);
  assert.equal(timerExerciseLogs(reviewed)[0].actual?.set_entries?.[0].load?.value, 27.5);
});

test("RPE round trips per set without turning varied effort into one aggregate", () => {
  const rows = [{ reps: "5", load: "100", rpe: "7" }, { reps: "5", load: "105", rpe: "8.5" }];
  const read = readSets(rows, "kg");
  assert.deepEqual(read.invalid, []);
  assert.equal(read.actual.effort, null);
  assert.deepEqual(draftsFromActual(read.actual), rows);
  assert.equal(readSets([rows[0]], "kg").actual.effort?.value, 7);
  for (const rpe of ["0", "11", "7.3", "bad"]) assert.deepEqual(readSets([{ ...rows[0], rpe }], "kg").invalid, [0]);
});

test("rest expiry starts the next set with pending measurements safely retained", () => {
  const items = buildTimerItems([{ blocks: [{ ...block, rest: { value: 30, unit: "s" } }] }]);
  let state = startItem(createTimerState(items), 0).state;
  state = completeSetWithResults(state, 1000).state;
  state.setDrafts!.press[0].load = "27.5";
  state = advance(state, 1_000_000).state;
  assert.equal(state.phase, "work");
  assert.equal(state.unit, 2);
  assert.equal(state.setDrafts!.press[0].load, "27.5");
  assert.deepEqual(unconfirmedSets(state), [{ itemId: "press", set: 1 }]);
  assert.equal(timerExerciseLogs(state)[0].actual?.set_entries?.[0].load, null);
});
