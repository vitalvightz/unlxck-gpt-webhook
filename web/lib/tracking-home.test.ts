import test from "node:test";
import assert from "node:assert/strict";

import { getTrackingHome } from "./tracking-home.ts";
import type { TrainingHistorySession } from "./training-history.ts";
import type { TodayCommandView } from "./types.ts";

const TODAY = "2026-10-19"; // Monday

const state = (today: Partial<TodayCommandView["today"]> = {}): TodayCommandView => ({
  active_plan: {},
  today: {
    training_day: TODAY, recommendation_state: "train_as_planned", decision_tier: "green",
    next_session: {}, session_scope: "none", session_label: "", completion_status: "not_started", ...today,
  },
  risk_watch: [], open_injuries: [], week_summary: {}, quick_actions: [],
} as TodayCommandView);

const row = (day: string, overrides: Partial<TrainingHistorySession> = {}): TrainingHistorySession => ({
  id: `${day}-${Math.random()}`, source: "external", training_day: day, status: "done", title: "Boxing · Pads",
  activity: "boxing", sport: "boxing", session_type: "pads", duration_minutes: 60, effort: "hard", plan_id: null, ...overrides,
});

const home = (overrides: Partial<Parameters<typeof getTrackingHome>[0]> = {}) => getTrackingHome({
  state: state(), rows: [], loadedFrom: null, today: TODAY, canCheckIn: true, ...overrides,
});

test("a restriction or safety notice leads exactly as on Today", () => {
  const result = home({ state: state({ recommendation_state: "pull_back", decision_tier: "stop" }), rows: [row(TODAY)] });
  assert.equal(result.hero.primary.label, "Open Today");
  assert.notEqual(result.hero.title, "Logged today");
});

test("not checked in asks for the check-in, but only with health-data consent", () => {
  const unchecked = state({ recommendation_state: "not_checked_in", decision_tier: "not_checked_in" });
  assert.equal(home({ state: unchecked }).hero.primary.href, "/today#today-checkin");
  assert.equal(home({ state: unchecked, canCheckIn: false }).hero.title, "Log your first session");
});

test("nothing logged: a first-session CTA and an empty strip; the slot shows readiness only if checked in", () => {
  const result = home();
  assert.deepEqual([result.hero.title, result.hero.primary.label], ["Log your first session", "Log session"]);
  assert.deepEqual(result.strip.map(cell => cell.value), ["0 sessions", "None", "None", "None"]);
  assert.equal(result.slot, "readiness");
  const unchecked = state({ recommendation_state: "not_checked_in", decision_tier: "not_checked_in" });
  assert.equal(home({ state: unchecked, canCheckIn: false }).slot, null);
});

test("logged today shows the session and the summary slot", () => {
  const result = home({ rows: [row(TODAY), row(TODAY, { title: "BJJ · Rolling", activity: "other", sport: "bjj", session_type: "rolling", duration_minutes: 90 })] });
  assert.equal(result.hero.title, "Logged today");
  assert.match(result.hero.lines[0], /^(Boxing · Pads · 60 min|BJJ · Rolling · 90 min) · \+1 more$/);
  assert.deepEqual(result.strip.map(cell => cell.value), ["2 sessions", "2h 30m", "BJJ", "Today"]);
  assert.equal(result.slot, "summary");
});

test("a learned weekly pattern becomes today's suggestion; otherwise the last session is shown", () => {
  const weekly = home({ rows: [row("2026-10-12"), row("2026-10-05")] });
  assert.equal(weekly.hero.title, "Suggested today");
  assert.equal(weekly.hero.lines[0], "Boxing · Pads · 60 min");
  const older = home({ rows: [row("2026-10-16")] });
  assert.equal(older.hero.title, "Log today's training");
  assert.equal(older.hero.lines[0], "Last: Boxing · Pads · 60 min · 3 days ago");
});

test("without recent training the slot falls back to readiness, then routines", () => {
  const old = [row("2026-08-01")];
  const ready = home({ rows: old });
  assert.equal(ready.slot, "readiness");
  assert.ok(ready.readiness?.title);
  const unchecked = state({ recommendation_state: "not_checked_in", decision_tier: "not_checked_in" });
  const habits = { enabled: true, decisions: [{ weekday: 0, activity: "other" as const, sport: "bjj" as const, session_type: "rolling" as const,
    duration_minutes: 90, state: "confirmed" as const, decided_on: "2026-10-01" }] };
  const routine = home({ state: unchecked, rows: old, canCheckIn: false, habits });
  assert.equal(routine.slot, "habits");
  assert.deepEqual(routine.routines, ["Monday · BJJ · Rolling · 90 min"]);
});

test("an unloaded or failed history claims nothing about training", () => {
  const result = home({ rows: null });
  assert.notEqual(result.hero.title, "Log your first session");
  assert.deepEqual(result.strip.map(cell => cell.value), ["None", "None", "None", "None"]);
  assert.equal(result.slot, "readiness");
});

test("incomplete week data is not shown as a total", () => {
  assert.equal(home({ rows: [row(TODAY)], loadedFrom: "2026-10-18" }).strip[0].value, "None");
});

test("the week cell is labelled as the rolling window it counts", () => {
  assert.equal(home().strip[0].label, "Last 7 days");
});

