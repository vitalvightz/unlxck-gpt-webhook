import assert from "node:assert/strict";
import test from "node:test";
import { customSchedulePrefill } from "./custom-plan-schedule";
import { openBlockWeekIntent } from "./open-block";
import { withLastLoad } from "./exercise-log";
import type { MeResponse } from "./types";

const onboarding = {
  profile: {
    full_name: "Ari",
    onboarding_draft: {
      athlete: { full_name: "Ari" }, no_scheduled_fight: true,
      training_availability: ["Monday", "Tuesday", "Thursday", "Friday"],
      hard_sparring_days: ["Monday"], support_work_days: ["Tuesday", "Thursday", "Friday"],
      session_types_by_day: { Tuesday: "strength", Thursday: "technical", Friday: "conditioning" },
    },
  },
  latest_intake: null,
} as unknown as MeResponse;

test("onboarding seeds hard contact and explicit technical days, never every support day", () => {
  const sessions = customSchedulePrefill(onboarding);
  assert.deepEqual(sessions.map(s => [s.weekday, s.session_type]), [["Monday", "sparring"], ["Thursday", "skill"]]);
  assert.equal(new Set(sessions.map(s => s.id)).size, 2);
  assert.deepEqual(sessions.map(s => s.exercises), [[], []]);
});

test("an athlete can edit, remove and add several sessions within the same calendar day", () => {
  const sessions = customSchedulePrefill(onboarding);
  const edited = [
    { ...sessions[0], name: "Technique", session_type: "skill" as const, weekday: "Thursday" as const },
    { ...sessions[1], name: "Second workout" },
  ];
  assert.equal(edited.filter(s => s.weekday === "Thursday").length, 2);
  assert.equal(sessions[0].weekday, "Monday");
});

test("missing onboarding does not invent sessions", () => {
  assert.deepEqual(customSchedulePrefill(null), []);
});

test("an explicit hard-sparring day type prefills even before its derived day list is saved", () => {
  const me = structuredClone(onboarding);
  me.profile.onboarding_draft = {
    ...(me.profile.onboarding_draft ?? {}), hard_sparring_days: [], session_types_by_day: { Monday: "hard_spar" },
  };
  assert.deepEqual(customSchedulePrefill(me).map(s => [s.weekday, s.session_type]), [["Monday", "sparring"]]);
});

test("custom week overlay does not prescribe automatic progression or deload", () => {
  for (let week = 1; week <= 4; week++) {
    assert.match(openBlockWeekIntent(week, true)!.summary, /saved prescription/);
    assert.doesNotMatch(openBlockWeekIntent(week, true)!.summary, /halve|half|cut|Progress again/);
  }
  assert.match(openBlockWeekIntent(4)!.summary, /half/); // existing AI presentation
});

test("as-prescribed logging never replaces an athlete's dose with a remembered load", () => {
  const request = { status: "as_prescribed" as const };
  const result = withLastLoad(
    { prescription_source: "athlete", display_name: "My squat", sets: 3, reps: 5 },
    request, [{ exercise_key: null, display_name: "My squat", training_day: "2026-10-05", load: { value: 100, unit: "kg" } }],
  );
  assert.deepEqual(result, request);
});
