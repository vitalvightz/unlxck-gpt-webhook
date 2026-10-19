import assert from "node:assert/strict";
import test from "node:test";
import type { ExercisePerformance } from "./api-schema.generated";
import { performanceValue, progressPoints, progressSeries } from "./exercise-progress";

const record = (id: string, day: string, performed_values: object | null): ExercisePerformance => ({
  id, training_day: day, performed_values, block: { name: "Squat", kind: "exercise", status: "as_prescribed", actual: {}, prescribed: { load: { value: 999, unit: "kg" } }, reason: null, notes: null, completed_dose: null, responses: [] },
}) as unknown as ExercisePerformance;

test("server eligibility is authoritative and zero/invalid values cannot create points", () => {
  assert.equal(performanceValue(record("1", "2026-10-01", null), "load"), null);
  assert.equal(performanceValue(record("2", "2026-10-01", { load: { value: 0, unit: "kg" } }), "load"), null);
  assert.equal(performanceValue(record("3", "2026-10-01", { reps: Number.NaN }), "reps"), null);
});

test("units and metrics stay separate with latest unit first, missing records break lines", () => {
  const records = [
    record("1", "2026-10-01", { load: { value: 80, unit: "kg" }, reps: 5 }),
    record("2", "2026-10-08", null),
    record("3", "2026-10-08", { load: { value: 90, unit: "kg" } }),
    record("4", "2026-10-19", { load: { value: 200, unit: "lb" }, duration: { value: 30, unit: "seconds" } }),
  ];
  const series = progressSeries(records);
  assert.deepEqual(series.map(item => item.id), ["load:lb", "load:kg", "reps:reps", "duration:seconds"]);
  assert.deepEqual(progressPoints(records, series[1]).map(point => [point.record.id, point.value]), [["1", 80], ["2", null], ["3", 90], ["4", null]]);
});
