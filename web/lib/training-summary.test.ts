import test from "node:test";
import assert from "node:assert/strict";

import { filterTakeaways, formatTrainingDuration, summarizeTraining } from "./training-summary.ts";
import type { TrainingHistorySession } from "@/lib/training-history";

const TODAY = "2026-10-19";

function row(overrides: Partial<TrainingHistorySession>): TrainingHistorySession {
  return {
    id: Math.random().toString(36), source: "external", training_day: TODAY, status: "done", title: "Boxing",
    activity: "boxing", duration_minutes: 60, effort: "hard", plan_id: null, ...overrides,
  };
}

test("the summary counts done and modified training in the window, by discipline", () => {
  const summary = summarizeTraining([
    row({ activity: "boxing", duration_minutes: 90 }),
    row({ activity: "boxing", duration_minutes: 150, training_day: "2026-10-13" }),
    row({ activity: "sparring", duration_minutes: 135 }),
    row({ activity: "strength", duration_minutes: 60 }),
    row({ activity: "conditioning", duration_minutes: 120, status: "modified" }),
    // Outside the 7-day window, skipped, or an unverified legacy completion.
    row({ activity: "boxing", training_day: "2026-10-12" }),
    row({ source: "unlxck", status: "skipped", completion_origin: "reported" }),
    row({ source: "unlxck", completion_origin: null, activity: null }),
  ], TODAY, 7);
  assert.equal(summary.sessions, 5);
  assert.equal(summary.minutes, 555);
  assert.equal(formatTrainingDuration(summary.minutes), "9h 15m");
  assert.deepEqual(summary.mix.map(item => [item.label, item.minutes]), [["Boxing", 240], ["S&C", 180], ["Sparring", 135]]);
});

test("plan sessions keep their own bucket and missing durations are never estimated", () => {
  const summary = summarizeTraining([
    row({ source: "unlxck", completion_origin: "reported", activity: null, duration_minutes: null, title: "Strength A" }),
    row({ activity: "roadwork", duration_minutes: 30 }),
  ], TODAY, 28);
  assert.equal(summary.sessions, 2);
  assert.equal(summary.minutes, 30);
  assert.equal(summary.untimed, 1);
  assert.deepEqual(summary.mix.map(item => item.label), ["Roadwork", "Unlxck plan"]);
});

test("the four-week window reaches 28 training days back", () => {
  const rows = [row({ training_day: "2026-09-22" }), row({ training_day: "2026-09-21" })];
  assert.equal(summarizeTraining(rows, TODAY, 28).sessions, 1);
  assert.equal(summarizeTraining([], TODAY, 7).sessions, 0);
});

test("durations format as hours and minutes", () => {
  assert.equal(formatTrainingDuration(0), "0m");
  assert.equal(formatTrainingDuration(45), "45m");
  assert.equal(formatTrainingDuration(120), "2h");
});

test("takeaways are found by their text or session title", () => {
  const rows = [
    row({ id: "a", takeaway: "Right hand up after the jab" }),
    row({ id: "b", title: "Roadwork", takeaway: "Hold pace on the hill" }),
    row({ id: "c", takeaway: "   " }),
    row({ id: "d" }),
  ];
  assert.deepEqual(filterTakeaways(rows, "").map(item => item.id), ["a", "b"]);
  assert.deepEqual(filterTakeaways(rows, "JAB").map(item => item.id), ["a"]);
  assert.deepEqual(filterTakeaways(rows, "roadwork").map(item => item.id), ["b"]);
});
