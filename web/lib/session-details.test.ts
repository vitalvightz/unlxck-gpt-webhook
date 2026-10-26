import assert from "node:assert/strict";
import test from "node:test";
import { detailMeasurements, matchesPrescription, measurementSummary } from "./session-details";

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
