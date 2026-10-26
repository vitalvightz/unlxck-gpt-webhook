import assert from "node:assert/strict";
import test from "node:test";
import { comparisonRows, detailMeasurements, matchesPrescription, measurementSummary, splitLoad } from "./session-details";

test("historical values retain their units, ranges, zeros, and applicable fields", () => {
  assert.deepEqual(detailMeasurements({ sets: 3, reps: "6–8", load: { value: 80, unit: "lb" },
    rest: { value: 0, unit: "seconds" }, effort: { method: "RPE", value: 8 }, internal: "secret" }), [
    { label: "Sets", value: "3" }, { label: "Reps", value: "6–8" }, { label: "Load", value: "80 lb" },
    { label: "Rest", value: "0 seconds" }, { label: "Effort", value: "RPE 8" },
  ]);
  assert.deepEqual(detailMeasurements({ duration_seconds: 45, sets: null, reps: undefined }), [{ label: "Duration", value: "45 sec" }]);
  assert.deepEqual(detailMeasurements({}), []);
});

test("collapsed summaries are one compact line and never include effort", () => {
  assert.equal(measurementSummary({ rounds: 3, work: { value: 180, unit: "seconds" }, rest: { value: 60, unit: "seconds" }, effort: { method: "RPE", value: 6 } }), "3 × 3 min · rest 1 min");
  assert.equal(measurementSummary({ sets: 3, reps: 5, load: { value: 8, unit: "kg" } }), "3 × 5 · 8 kg");
  assert.equal(measurementSummary({ sets: 2, set_entries: [{ reps: 3, load: { value: 25, unit: "kg" } }, { reps: 3, load: { value: 30, unit: "kg" } }] }), "2 × 3 · 25–30 kg");
  assert.equal(measurementSummary({ prescription_text: " 3 × 180s · rest 60s " }), "3 × 180s · rest 60s");
  assert.equal(measurementSummary({ reps: 5 }), "5 reps");
  assert.equal(measurementSummary({}), "");
});

test("reported values only match when they repeat the prescription exactly", () => {
  assert.equal(matchesPrescription({ sets: 4, reps: 2 }, { sets: 4, set_entries: [{ reps: 2 }, { reps: 2 }, { reps: 2 }, { reps: 2 }] }), true);
  assert.equal(matchesPrescription({ sets: 4, reps: 2 }, { sets: 4, set_entries: [{ reps: 2 }, { reps: 2 }, { reps: 2 }, { reps: 1 }] }), false);
  assert.equal(matchesPrescription({ sets: 4, reps: 2 }, { set_entries: [{ reps: 2, load: { value: 20, unit: "kg" } }] }), false);
  assert.equal(matchesPrescription({ sets: 3, reps: 5, load: { value: 80, unit: "kg" } }, { load: { value: 80, unit: "kg" } }), true);
  assert.equal(matchesPrescription({ sets: 3, reps: 5 }, { load: { value: 80, unit: "kg" } }), false);
  assert.equal(matchesPrescription({ sets: 3 }, {}), false);
});

test("the weight stands apart from the dose so it can be shown on its own", () => {
  assert.deepEqual(splitLoad({ sets: 2, set_entries: [{ reps: 3, load: { value: 25, unit: "kg" } }, { reps: 3, load: { value: 30, unit: "kg" } }], rest: { value: 90, unit: "seconds" } }),
    { load: "25–30 kg", dose: "2 × 3 · rest 90 sec" });
  assert.deepEqual(splitLoad({ sets: 3, reps: 5, load: { value: 80, unit: "kg" } }), { load: "80 kg", dose: "3 × 5" });
  assert.deepEqual(splitLoad({ sets: 4, reps: 6, load: { display: "Choose a controlled load" } }), { load: null, dose: "4 × 6 · Choose a controlled load" });
  assert.deepEqual(splitLoad({ rounds: 3, work: { value: 180, unit: "seconds" } }), { load: null, dose: "3 × 3 min" });
});

test("comparison rows pair done and planned values without inventing either", () => {
  assert.deepEqual(comparisonRows({ sets: 4, reps: 6, load: { value: 80, unit: "kg" } }, { sets: 3, reps: 6, load: { value: 75, unit: "kg" } }), [
    { label: "Sets", did: "3", plan: "4", same: false }, { label: "Reps", did: "6", plan: "6", same: true }, { label: "Load", did: "75 kg", plan: "80 kg", same: false },
  ]);
  assert.deepEqual(comparisonRows({ sets: 2, reps: 3 }, { set_entries: [{ reps: 3, load: { value: 20, unit: "kg" } }, { reps: 2, load: { value: 22, unit: "kg" } }] }), [
    { label: "Sets", did: "2", plan: "2", same: true }, { label: "Reps", did: "2–3", plan: "3", same: false }, { label: "Load", did: "20–22 kg", plan: undefined, same: false },
  ]);
  assert.deepEqual(comparisonRows({ rounds: 3 }, {}), [{ label: "Rounds", did: undefined, plan: "3", same: false }]);
});
