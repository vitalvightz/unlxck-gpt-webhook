import assert from "node:assert/strict";
import test from "node:test";
import type { TrainingHistorySession } from "./training-history";
import { rhythmWindowDays, trainingWeeks, weekComparison, weekStart, weekValue } from "./training-rhythm";

const row = (id: string, day: string, changes: Partial<TrainingHistorySession> = {}): TrainingHistorySession => ({
  id, source: "external", training_day: day, status: "done", title: "Boxing", activity: "boxing",
  duration_minutes: 45, effort: "hard", plan_id: null, ...changes,
});

test("local calendar weeks cross DST and year boundaries without timezone shifts", () => {
  assert.equal(weekStart("2026-10-25"), "2026-10-19");
  assert.equal(weekStart("2027-01-01"), "2026-12-28");
  assert.equal(weekStart("2026-03-29"), "2026-03-23");
  assert.equal(rhythmWindowDays("2026-10-19", 12), 78);
  assert.equal(rhythmWindowDays("2026-10-25", 12), 84);
});

test("whole weeks count reported/manual work, distinct same-day identities, and honest gaps", () => {
  const manual = row("one", "2026-10-18");
  const weeks = trainingWeeks([
    manual, manual, row("two", "2026-10-18", { duration_minutes: null }),
    row("one", "2026-10-18", { source: "unlxck", completion_origin: "reported", status: "modified" }),
    row("skip", "2026-10-18", { status: "skipped" }),
    row("credit", "2026-10-18", { source: "unlxck", completion_origin: "day_credit" }),
    row("legacy", "2026-10-18", { source: "unlxck", completion_origin: null }),
    row("future", "2026-10-20"), row("invalid", "not-a-date"),
    row("old", "2026-09-28"),
  ], "2026-10-19", 4);
  assert.deepEqual(weeks.map(week => week.sessions), [1, 0, 3, 0]);
  assert.equal(weeks[2].minutes, 90);
  assert.equal(weeks[2].untimed, 1);
  assert.equal(weeks[3].current, true);
  assert.equal(trainingWeeks([manual], "2026-10-19", 4, "unlxck")[2].sessions, 0);
  assert.equal(trainingWeeks([manual], "2026-10-19", 4, "boxing")[2].sessions, 1);
});

test("recorded-minute comparisons identify missing durations in either week", () => {
  const weeks = trainingWeeks([
    row("prev", "2026-10-11"), row("unknown-prev", "2026-10-11", { duration_minutes: null }),
    row("last", "2026-10-18", { duration_minutes: 60 }), row("unknown-last", "2026-10-18", { duration_minutes: null }),
    row("current", "2026-10-19", { duration_minutes: 500 }),
  ], "2026-10-19", 4);
  assert.equal(weekComparison(weeks, "minutes"), "+15 recorded minutes versus the previous week. Missing durations: 1 last completed week; 1 previous week.");
  assert.equal(weekComparison(weeks, "sessions"), "No change in sessions versus the previous week.");
  const untimed = trainingWeeks([row("unknown", "2026-10-18", { duration_minutes: null })], "2026-10-19", 4)[2];
  assert.equal(weekValue(untimed, "minutes"), null);
  assert.equal(weekValue(weeks[0], "minutes"), 0);
});

test("recorded-minute comparisons are unavailable when neither week has a duration", () => {
  const untimed = { duration_minutes: null };
  const both = trainingWeeks([row("prev", "2026-10-11", untimed), row("last", "2026-10-18", untimed), row("last-2", "2026-10-18", untimed)], "2026-10-19", 4);
  assert.equal(weekComparison(both, "minutes"), "Training time comparison unavailable. Neither week has recorded durations.");
  assert.equal(weekComparison(both, "sessions"), "+1 session versus the previous week.");
  const oneEmpty = trainingWeeks([row("last", "2026-10-18", untimed)], "2026-10-19", 4);
  assert.equal(weekComparison(oneEmpty, "minutes"), "Training time comparison unavailable. Neither week has recorded durations.");
  assert.equal(weekComparison(trainingWeeks([], "2026-10-19", 4), "minutes"), "No change in recorded minutes versus the previous week.");
});
