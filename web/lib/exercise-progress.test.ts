import assert from "node:assert/strict";
import test from "node:test";
import type { ExercisePerformance } from "./api-schema.generated";
import { measurementCount, performanceValue, progressPoints, progressSeries, type ProgressSeries } from "./exercise-progress";

const record = (id: string, day: string, performed_values: object | null): ExercisePerformance => ({
  id, training_day: day, performed_values, block: { name: "Squat", kind: "exercise", status: "as_prescribed", actual: {}, prescribed: { load: { value: 999, unit: "kg" } }, reason: null, notes: null, completed_dose: null, responses: [] },
}) as unknown as ExercisePerformance;

test("server eligibility is authoritative and zero/invalid values cannot create points", () => {
  assert.equal(performanceValue(record("1", "2026-10-01", null), "load"), null);
  assert.equal(performanceValue(record("2", "2026-10-01", { load: { value: 0, unit: "kg" } }), "load"), null);
  assert.equal(performanceValue(record("3", "2026-10-01", { reps: Number.NaN }), "reps"), null);
});

const kg: ProgressSeries = { id: "load:kg", metric: "load", label: "Load", unit: "kg" };
const plot = (records: ExercisePerformance[], series = kg) => progressPoints(records, series).map(point => [point.record.id, point.value]);

test("units and metrics stay separate with latest unit first; ineligible records are dropped, not gapped", () => {
  const records = [
    record("1", "2026-10-01", { load: { value: 80, unit: "kg" }, reps: 5 }),
    record("2", "2026-10-08", null),
    record("3", "2026-10-08", { load: { value: 90, unit: "kg" } }),
    record("4", "2026-10-19", { load: { value: 200, unit: "lb" }, duration: { value: 30, unit: "seconds" } }),
  ];
  const series = progressSeries(records);
  assert.deepEqual(series.map(item => item.id), ["load:lb", "load:kg", "reps:reps", "duration:seconds"]);
  assert.deepEqual(plot(records, series[1]), [["1", 80], ["3", 90]]);
  assert.deepEqual(plot(records, series[0]), [["4", 200]]);
  assert.deepEqual(plot(records, series[3]), [["4", 30]]);
});

test("Med-Ball Rotational Throw: an earlier load-less session does not reach the load series", () => {
  const records = [
    record("a", "2026-10-10", { reps: 8 }),
    record("b", "2026-10-19", { load: { value: 8, unit: "kg" } }),
    record("c", "2026-10-21", { load: { value: 15, unit: "kg" } }),
    record("d", "2026-10-22", { load: { value: 22, unit: "kg" } }),
  ];
  const points = progressPoints(records, kg);
  assert.deepEqual(points.map(point => point.value), [8, 15, 22]);
  assert.equal(points[0].record.training_day, "2026-10-19"); // axis starts at the first eligible date
  assert.equal(measurementCount(points.length, "load"), "3 recorded loads");
  assert.deepEqual(plot(records, { id: "reps:reps", metric: "reps", label: "Reps", unit: "reps" }), [["a", 8]]);
});

test("zero, one and many eligible measurements", () => {
  assert.deepEqual(plot([record("1", "2026-10-01", null), record("2", "2026-10-02", { reps: 5 })]), []);
  assert.deepEqual(plot([record("1", "2026-10-01", { load: { value: 60, unit: "kg" } })]), [["1", 60]]);
  assert.deepEqual(plot([
    record("2", "2026-10-09", { load: { value: 70, unit: "kg" } }),
    record("1", "2026-10-01", { load: { value: 60, unit: "kg" } }),
    record("3", "2026-10-12", { load: { value: 65, unit: "kg" } }),
  ]), [["1", 60], ["2", 70], ["3", 65]]);
});

test("explicit zero and missing loads are both excluded and never plotted as zero", () => {
  const points = progressPoints([
    record("1", "2026-10-01", { load: { value: 0, unit: "kg" } }),
    record("2", "2026-10-02", { load: null }),
    record("3", "2026-10-03", {}),
    record("4", "2026-10-04", { load: { value: Number.NaN, unit: "kg" } }),
    record("5", "2026-10-05", { load: { value: 40, unit: "kg" } }),
  ], kg);
  assert.deepEqual(points.map(point => [point.record.id, point.value]), [["5", 40]]);
  assert.ok(points.every(point => point.value > 0));
});

test("unconfirmed prescriptions never supply a value; the server's performed projection does", () => {
  // The fixture prescribes 999 kg on every record; only performed_values may plot.
  assert.deepEqual(plot([record("1", "2026-10-01", null), record("2", "2026-10-02", { reps: 5 })]), []);
  const confirmed = record("3", "2026-10-03", { load: { value: 50, unit: "kg" } });
  const reported = { ...record("4", "2026-10-04", { load: { value: 55, unit: "kg" } }), block: { ...confirmed.block, status: "modified", actual: { load: { value: 55, unit: "kg" } } } } as ExercisePerformance;
  assert.deepEqual(plot([confirmed, reported]), [["3", 50], ["4", 55]]);
});

test("counts are metric-specific", () => {
  assert.equal(measurementCount(1, "load"), "1 recorded load");
  assert.equal(measurementCount(2, "duration"), "2 recorded durations");
  assert.equal(measurementCount(1, "reps"), "1 recorded rep count");
  assert.equal(measurementCount(4, "distance"), "4 recorded distances");
});
