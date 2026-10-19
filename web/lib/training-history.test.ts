import assert from "node:assert/strict";
import test from "node:test";
import { canRepeatTraining, latestRepeatableTraining, type TrainingHistorySession } from "./training-history";

const manual: TrainingHistorySession = {
  id: "manual", source: "external", training_day: "2026-10-09", status: "done", title: "Sparring",
  activity: "sparring", duration_minutes: 60, effort: "hard", plan_id: null,
};

test("repeat selects the latest eligible manual session without mutating history", () => {
  const newer = { ...manual, id: "newer", training_day: "2026-10-10" };
  const rows = [manual, { ...newer, id: "prescribed", source: "unlxck" as const }, newer];
  const before = structuredClone(rows);
  assert.equal(latestRepeatableTraining(rows), newer);
  assert.deepEqual(rows, before);
  assert.equal(latestRepeatableTraining([]), undefined);
  for (const change of [{ source: "unlxck" }, { status: "skipped" }, { activity: null }, { activity: "unknown" },
    { duration_minutes: null }, { duration_minutes: 0 }, { duration_minutes: 601 }, { duration_minutes: 1.5 }, { effort: null }]) {
    assert.equal(canRepeatTraining({ ...manual, ...change } as TrainingHistorySession), false);
  }
  assert.equal(latestRepeatableTraining([newer, { ...newer, id: "earlier" }]), newer);
});

test("repeat keeps a classified session and rejects an inconsistent one", () => {
  const rolling = { ...manual, activity: "other" as const, sport: "bjj" as const, session_type: "rolling" as const };
  assert.equal(canRepeatTraining(rolling), true);
  assert.equal(canRepeatTraining({ ...rolling, activity: "sparring" }), false);
  assert.equal(canRepeatTraining({ ...manual, sport: null, session_type: null }), true);
});
