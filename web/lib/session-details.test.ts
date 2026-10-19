import assert from "node:assert/strict";
import test from "node:test";
import { detailMeasurements } from "./session-details";

test("historical values retain their units, ranges, zeros, and applicable fields", () => {
  assert.deepEqual(detailMeasurements({ sets: 3, reps: "6–8", load: { value: 80, unit: "lb" },
    rest: { value: 0, unit: "seconds" }, effort: { method: "RPE", value: 8 }, internal: "secret" }), [
    { label: "Sets", value: "3" }, { label: "Reps", value: "6–8" }, { label: "Load", value: "80 lb" },
    { label: "Rest", value: "0 seconds" }, { label: "Effort", value: "RPE 8" },
  ]);
  assert.deepEqual(detailMeasurements({ duration_seconds: 45, sets: null, reps: undefined }), [{ label: "Duration", value: "45 sec" }]);
  assert.deepEqual(detailMeasurements({}), []);
});
