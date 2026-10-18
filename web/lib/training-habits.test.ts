import assert from "node:assert/strict";
import test from "node:test";
import { decideTrainingHabit, EMPTY_TRAINING_HABITS, habitTrainingDay, habitWeekday, learnTrainingHabits, type TrainingHabitPreferences } from "./training-habits";
import type { TrainingActivity, TrainingHistorySession } from "./training-history";
const today = "2026-10-19"; // Monday
const row = (day: string, activity: TrainingActivity = "boxing", minutes = 60, id = `${day}-${activity}`): TrainingHistorySession => ({
  id, training_day: day, activity, duration_minutes: minutes, effort: "hard", title: activity, source: "external", status: "done", plan_id: null,
});
const history = [row("2026-10-12"), row("2026-10-05")];
const confirmed: TrainingHabitPreferences = { enabled: true, decisions: [{ weekday: 0, activity: "boxing", duration_minutes: 50, state: "confirmed", decided_on: "2026-09-20" }] };

test("one manual session starts a tentative weekday suggestion, never a routine", () => {
  const result = learnTrainingHabits([history[0]], today);
  assert.equal(result.suggestion?.title, "Suggested today");
  assert.equal(result.suggestion?.activity, "boxing");
  assert.equal(result.prompt, undefined);
  assert.equal(learnTrainingHabits([row("2026-10-13")], today).suggestion, undefined);
  assert.equal(habitWeekday(today), 0);
  assert.equal(habitWeekday("2026-10-18"), 6);
});

test("two consecutive weekday dates qualify, multiple entries or retries on one date do not", () => {
  assert.equal(learnTrainingHabits(history, today).prompt?.activity, "boxing");
  assert.equal(learnTrainingHabits([history[0], history[0], row("2026-10-12", "boxing", 20, "second")], today).prompt, undefined);
  assert.equal(learnTrainingHabits([history[0], row("2026-09-28")], today).prompt, undefined);
});

test("future, prescribed, skipped, malformed and old sessions cannot teach a pattern", () => {
  const invalid = [row("2026-10-26"), row("2026-08-31"), row("2026-02-30"),
    { ...history[0], source: "unlxck" as const }, { ...history[1], status: "skipped" as const }];
  assert.equal(learnTrainingHabits(invalid, today).suggestion, undefined);
  assert.equal(learnTrainingHabits([], "bad-day").suggestion, undefined);
  assert.equal(learnTrainingHabits([row("2026-09-28")], today).suggestion, undefined);
});

test("recent observations lead unconfirmed history; recent per-day medians resist outliers", () => {
  const rows = [row("2026-10-12", "strength", 40), ...["2026-10-05", "2026-09-28", "2026-09-21"].map(day => row(day))];
  assert.equal(learnTrainingHabits(rows, today).suggestion?.activity, "strength");
  const result = learnTrainingHabits([...history, row("2026-09-28", "boxing", 600), row("2026-10-12", "boxing", 30, "extra")], today);
  assert.equal(result.suggestion?.duration_minutes, 60);
});

test("confirmation wins over one-off changes; today's actual logging suppresses guesses", () => {
  assert.equal(learnTrainingHabits([row("2026-10-12", "strength")], today, confirmed).suggestion?.activity, "boxing");
  assert.equal(learnTrainingHabits([row(today, "strength"), ...history], today, confirmed).suggestion, undefined);
  assert.equal(learnTrainingHabits(history, today, confirmed).suggestion?.duration_minutes, 50);
  assert.equal(learnTrainingHabits(history, today, confirmed).prompt, undefined);
});

test("two changed weekdays offer an update, without overwriting the confirmed routine", () => {
  const before = structuredClone(confirmed);
  const result = learnTrainingHabits([row("2026-10-12", "strength"), row("2026-10-05", "strength")], today, confirmed);
  assert.equal(result.prompt?.replace?.activity, "boxing");
  assert.equal(result.suggestion?.activity, "boxing");
  assert.deepEqual(confirmed, before);
  const both = learnTrainingHabits([row("2026-10-12", "strength"), row("2026-10-05", "strength"), ...history], today, confirmed);
  assert.equal(both.prompt?.replace, undefined); // Additional sessions are not assumed to replace boxing.
});

test("declining asks once, and explicit replacement preserves other weekday routines", () => {
  const declined = decideTrainingHabit(EMPTY_TRAINING_HABITS, { weekday: 0, activity: "boxing", duration_minutes: 60, state: "dismissed", decided_on: today });
  assert.equal(learnTrainingHabits(history, today, declined).prompt, undefined);
  assert.equal(learnTrainingHabits(history, today, declined).suggestion, undefined);
  const before = structuredClone(confirmed);
  const changed = decideTrainingHabit(confirmed, { weekday: 0, activity: "strength", duration_minutes: 40, state: "confirmed", decided_on: today }, confirmed.decisions[0]);
  assert.equal(changed.decisions.find(item => item.activity === "boxing")?.state, "dismissed");
  assert.equal(changed.decisions.find(item => item.activity === "strength")?.state, "confirmed");
  assert.deepEqual(confirmed, before);
});

test("coach schedules, safety restrictions, opt-out and truncated evidence suppress inference", () => {
  for (const options of [{ coachScheduled: true }, { restricted: true }, { truncated: true }]) {
    const result = learnTrainingHabits(history, today, confirmed, options);
    assert.equal(result.suggestion, undefined); assert.equal(result.prompt, undefined);
  }
  assert.equal(learnTrainingHabits(history, today, { ...confirmed, enabled: false }).suggestion, undefined);
});

test("sparring never becomes a learned suggestion without explicit permission", () => {
  const contact = history.map(item => ({ ...item, activity: "sparring" as const }));
  assert.equal(learnTrainingHabits(contact, today).suggestion, undefined);
  const routine = { ...confirmed, decisions: confirmed.decisions.map(item => ({ ...item, activity: "sparring" as const })) };
  assert.equal(learnTrainingHabits(contact, today, routine).suggestion, undefined);
  assert.equal(learnTrainingHabits(contact, today, routine, { allowSparring: true }).suggestion?.activity, "sparring");
  assert.equal(learnTrainingHabits(contact, today, routine, { allowSparring: true, restricted: true }).suggestion, undefined);
});

test("multiple activities can be confirmed on the same weekday without merging sessions", () => {
  const two = decideTrainingHabit(confirmed, { weekday: 0, activity: "strength", duration_minutes: 45, state: "confirmed", decided_on: today });
  assert.equal(two.decisions.filter(item => item.state === "confirmed").length, 2);
  assert.equal(learnTrainingHabits([row(today), ...history], today, two).suggestion?.activity, "strength");
  assert.equal(learnTrainingHabits([row(today, "roadwork"), ...history], today, two).suggestion, undefined);
  assert.equal(learnTrainingHabits([], "2026-10-26", two).suggestion?.activity, "boxing");
});


test("learning follows athlete timezone and 03:00 rollover, with the API's UTC fallback", () => {
  const early = new Date("2026-10-19T06:30:00Z");
  assert.equal(habitTrainingDay(early, "America/New_York"), "2026-10-18");
  assert.equal(habitTrainingDay(new Date("2026-10-19T07:30:00Z"), "America/New_York"), "2026-10-19");
  assert.equal(habitTrainingDay(early, "not-a-zone"), "2026-10-19");
  assert.equal(habitTrainingDay(early, ""), "2026-10-19");
});
