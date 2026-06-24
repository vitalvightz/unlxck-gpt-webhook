import test from "node:test";
import assert from "node:assert/strict";

import {
  dayCompletion,
  deriveCountdownLabel,
  findDayByISO,
  getReadinessStrip,
  resolveCurrentDay,
  resolveNextPlanFocusDay,
  resolvePlanProgress,
  resolveTrainingDay,
  sessionIdentity,
  toISODate,
  weekCompletion,
  weekLoadProxy,
  weekSessionSummary,
} from "./camp-map.ts";
import type { StructuredPlan } from "@/lib/types";

function campPlan(): StructuredPlan {
  return {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    event_context: { fight_date: "2026-07-17" },
    red_flag_rules: [
      { rule_id: "rf-1", severity: "red", display_text: "Stop if Achilles pain ≥ 6/10." },
    ],
    weeks: [
      {
        week_id: "wk-1",
        week_index: 1,
        phase_label: "SPP",
        week_goal: "Convert strength into speed.",
        days: [
          {
            date: "2026-06-18",
            day_type: "high",
            countdown_label: "D-29",
            sessions: [
              { session_id: "s1", title: "Lower power", completion_status: "done", blocks: [] },
              { session_id: "s2", title: "Sprint", completion_status: "not_started", blocks: [] },
            ],
          },
          {
            date: "2026-06-19",
            day_type: "moderate",
            countdown_label: "D-28",
            today_card: {
              headline: "Speed conversion",
              readiness_status: "train_as_planned",
              primary_warning: "Achilles still tender — keep contacts short.",
            },
            sessions: [
              { session_id: "s3", title: "Upper strength", completion_status: "done", blocks: [] },
            ],
          },
        ],
      },
      {
        week_id: "wk-2",
        week_index: 2,
        phase_label: "TAPER",
        week_goal: "Sharpen and freshen.",
        days: [{ date: "2026-06-25", day_type: "low", sessions: [] }],
      },
    ],
  } satisfies StructuredPlan;
}

test("toISODate formats a Date as a local YYYY-MM-DD string", () => {
  assert.equal(toISODate(new Date(2026, 5, 19)), "2026-06-19");
  assert.equal(toISODate(new Date(2026, 0, 3)), "2026-01-03");
});

test("resolvePlanProgress locates today's week, day and countdown", () => {
  const progress = resolvePlanProgress(campPlan(), new Date(2026, 5, 19));
  assert.equal(progress.weekCount, 2);
  assert.equal(progress.currentWeekPos, 0);
  assert.equal(progress.currentDayDate, "2026-06-19");
  assert.equal(progress.dLabel, "D-28");
});

test("resolvePlanProgress falls back to a derived countdown when out of range", () => {
  const progress = resolvePlanProgress(campPlan(), new Date(2026, 5, 1));
  assert.equal(progress.currentWeekPos, null);
  assert.equal(progress.currentDayDate, null);
  // 2026-07-17 minus 2026-06-01 = 46 days.
  assert.equal(progress.dLabel, "D-46");
});

test("resolvePlanProgress tolerates an empty/missing plan", () => {
  const progress = resolvePlanProgress(undefined, new Date(2026, 5, 19));
  assert.equal(progress.weekCount, 0);
  assert.equal(progress.currentWeekPos, null);
  assert.equal(progress.dLabel, null);
});

test("deriveCountdownLabel returns D0 on event day and null after it", () => {
  assert.equal(deriveCountdownLabel(campPlan(), new Date(2026, 6, 17)), "D0");
  assert.equal(deriveCountdownLabel(campPlan(), new Date(2026, 6, 18)), null);
});

test("weekCompletion and dayCompletion count done sessions", () => {
  const plan = campPlan();
  const week1 = plan.weeks![0]!;
  assert.deepEqual(weekCompletion(week1), { done: 2, total: 3 });
  assert.deepEqual(dayCompletion(week1.days![0]!), { done: 1, total: 2 });
  assert.deepEqual(dayCompletion(week1.days![1]!), { done: 1, total: 1 });
});

test("weekSessionSummary separates app sessions from coach-led days", () => {
  const week = {
    days: [
      {
        date: "2026-06-18",
        sessions: [{ session_id: "s1", title: "Lower strength", blocks: [] }],
      },
      {
        date: "2026-06-19",
        sessions: [{ session_id: "s2", title: "Conditioning", blocks: [] }],
      },
      {
        date: "2026-06-20",
        today_card: { headline: "Coach-led boxing session" },
        sessions: [],
      },
      {
        date: "2026-06-21",
        today_card: { headline: "Coach-led sparring" },
        sessions: [],
      },
      {
        date: "2026-06-22",
        day_type: "rest",
        sessions: [],
      },
    ],
  };

  assert.deepEqual(weekSessionSummary(week), {
    trainingDays: 4,
    appSessions: 2,
    coachLedSessions: 2,
  });
});

test("weekLoadProxy returns the most demanding day type, titleized", () => {
  const plan = campPlan();
  assert.equal(weekLoadProxy(plan.weeks![0]!), "High");
  assert.equal(weekLoadProxy(plan.weeks![1]!), "Low");
  assert.equal(weekLoadProxy({ days: [] }), null);
});

test("findDayByISO returns the matching day or null", () => {
  const plan = campPlan();
  assert.equal(findDayByISO(plan, "2026-06-19")?.day_type, "moderate");
  assert.equal(findDayByISO(plan, "2026-12-25"), null);
  assert.equal(findDayByISO(plan, null), null);
});

test("getReadinessStrip surfaces focus, risk and load (never the today call)", () => {
  const plan = campPlan();
  const currentDay = findDayByISO(plan, "2026-06-19");
  const strip = getReadinessStrip(plan, currentDay, plan.weeks![0]);
  // Focus falls back to the day's headline; risk to its primary_warning; load to
  // the week proxy. The exact "train / modify / pull back" call is owned by Today
  // and never surfaces here; phase is left to the CampStatusLine.
  assert.equal(strip.focus, "Speed conversion");
  assert.equal(strip.risk, "Achilles still tender — keep contacts short.");
  assert.equal(strip.load, "High");
  assert.equal("todayCall" in strip, false);
  assert.equal("phase" in strip, false);
});

test("getReadinessStrip prefers an explicit readiness_snapshot over derived values", () => {
  const plan: StructuredPlan = {
    ...campPlan(),
    // today_call is ignored on the plan page (it belongs to Today); the strip
    // reads only focus / injury_watch / weekly_load from the snapshot.
    readiness_snapshot: {
      today_call: "Pull back",
      focus: "Tendon capacity",
      injury_watch: "Achilles flaring — cap plyo volume.",
      weekly_load: "Moderate-high",
    },
  };
  const currentDay = findDayByISO(plan, "2026-06-19");
  const strip = getReadinessStrip(plan, currentDay, plan.weeks![0]);
  assert.equal(strip.focus, "Tendon capacity");
  assert.equal(strip.risk, "Achilles flaring — cap plyo volume.");
  assert.equal(strip.load, "Moderate-high");
});

test("getReadinessStrip degrades gracefully with no current day", () => {
  const plan = campPlan();
  // No current day: focus has nothing to derive from, risk falls back to the top
  // red flag, and load comes from the passed week proxy.
  const strip = getReadinessStrip(plan, null, plan.weeks![1]);
  assert.equal(strip.focus, null);
  assert.equal(strip.risk, "Stop if Achilles pain ≥ 6/10.");
  assert.equal(strip.load, "Low");
});

test("resolveTrainingDay applies the 04:00 athlete-local rollover", () => {
  // Before 04:00 the training day has not advanced yet — it is still yesterday.
  assert.equal(toISODate(resolveTrainingDay(new Date(2026, 5, 19, 2, 30))), "2026-06-18");
  // At/after 04:00 the training day is today.
  assert.equal(toISODate(resolveTrainingDay(new Date(2026, 5, 19, 4, 0))), "2026-06-19");
  assert.equal(toISODate(resolveTrainingDay(new Date(2026, 5, 19, 23, 59))), "2026-06-19");
});

test("resolveTrainingDay returns local midnight of the resolved day", () => {
  const resolved = resolveTrainingDay(new Date(2026, 5, 19, 15, 42, 13));
  assert.equal(resolved.getHours(), 0);
  assert.equal(resolved.getMinutes(), 0);
  assert.equal(resolved.getSeconds(), 0);
});

test("resolveCurrentDay locates today's week, day, sessions and countdown", () => {
  const current = resolveCurrentDay(campPlan(), new Date(2026, 5, 19));
  assert.equal(current.inRange, true);
  assert.equal(current.weekPos, 0);
  assert.equal(current.dayPos, 1);
  assert.equal(current.sessions.length, 1);
  assert.equal(current.sessions[0]?.title, "Upper strength");
  assert.equal(current.dLabel, "D-28");
});

test("resolveCurrentDay reports an in-range off day with no sessions", () => {
  const current = resolveCurrentDay(campPlan(), new Date(2026, 5, 25));
  assert.equal(current.inRange, true);
  assert.equal(current.weekPos, 1);
  assert.equal(current.dayPos, 0);
  assert.equal(current.sessions.length, 0);
});

test("resolveCurrentDay is out of range when today maps to no day", () => {
  const current = resolveCurrentDay(campPlan(), new Date(2026, 5, 1));
  assert.equal(current.inRange, false);
  assert.equal(current.weekPos, null);
  assert.equal(current.dayPos, null);
  assert.equal(current.sessions.length, 0);
  // Still derives a countdown from the event date when out of range.
  assert.equal(current.dLabel, "D-46");
});

test("resolveCurrentDay agrees with resolvePlanProgress on the current day", () => {
  const plan = campPlan();
  const today = new Date(2026, 5, 19);
  const progress = resolvePlanProgress(plan, today);
  const current = resolveCurrentDay(plan, today);
  assert.equal(current.weekPos, progress.currentWeekPos);
  assert.equal(current.trainingDayISO, progress.currentDayDate);
  assert.equal(current.dLabel, progress.dLabel);
});

test("resolveCurrentDay treats a null today as no current day (SSR-safe)", () => {
  // Before the client mounts the training day is null; this must resolve to
  // "no current day" rather than matching a day with a missing date.
  const current = resolveCurrentDay(campPlan(), null);
  assert.equal(current.inRange, false);
  assert.equal(current.trainingDayISO, null);
  assert.equal(current.weekPos, null);
  assert.equal(current.sessions.length, 0);
  assert.equal(current.dLabel, null);
});

test("resolveNextPlanFocusDay prefers the next unfinished app card before a later coach-led day", () => {
  const plan = {
    weeks: [
      {
        days: [
          {
            date: "2026-06-23",
            countdown_label: "D-9",
            sessions: [{ session_id: "tue", title: "Single-leg power", completion_status: "done" }],
          },
          {
            date: "2026-06-26",
            countdown_label: "D-6",
            sessions: [{ session_id: "fri", title: "Friday app session", completion_status: "not_started" }],
          },
          {
            date: "2026-06-27",
            countdown_label: "D-5",
            today_card: { headline: "Technical work" },
            sessions: [],
          },
        ],
      },
    ],
  } as StructuredPlan;

  const focus = resolveNextPlanFocusDay(plan, new Date(2026, 5, 23), new Date(2026, 5, 27));

  assert.equal(focus && toISODate(focus), "2026-06-26");
});

test("resolveNextPlanFocusDay falls through to coach-led day after app cards are terminal", () => {
  const plan = {
    weeks: [
      {
        days: [
          {
            date: "2026-06-23",
            sessions: [{ session_id: "tue", completion_status: "done" }],
          },
          {
            date: "2026-06-26",
            sessions: [{ session_id: "fri", completion_status: "skipped" }],
          },
          {
            date: "2026-06-27",
            today_card: { headline: "Technical work" },
            sessions: [],
          },
        ],
      },
    ],
  } as StructuredPlan;

  const focus = resolveNextPlanFocusDay(plan, new Date(2026, 5, 23), new Date(2026, 5, 27));

  assert.equal(focus && toISODate(focus), "2026-06-27");
});

test("resolvePlanProgress treats a null today as out of range (SSR-safe)", () => {
  const progress = resolvePlanProgress(campPlan(), null);
  assert.equal(progress.currentWeekPos, null);
  assert.equal(progress.currentDayDate, null);
  assert.equal(progress.dLabel, null);
});

test("sessionIdentity prefers plan + day + session_id", () => {
  const plan = campPlan();
  const day = plan.weeks![0]!.days![1]!;
  const session = day.sessions![0]!;
  assert.equal(
    sessionIdentity({ planId: "plan-1", weekPos: 0, dayPos: 1, sessionPos: 0, day, session }),
    "plan-1|2026-06-19|s3",
  );
});

test("sessionIdentity falls back to plan + week/day/session indices", () => {
  // No session_id and no day date -> stable index-based identity.
  assert.equal(
    sessionIdentity({
      planId: "plan-1",
      weekPos: 2,
      dayPos: 3,
      sessionPos: 1,
      day: { sessions: [] },
      session: {},
    }),
    "plan-1|w2|d3|s1",
  );
});

test("sessionIdentity keys the day portion on the parent day's date", () => {
  // The parent day owns the date; identity must not key on anything else.
  const day = { date: "2026-06-19", sessions: [] };
  assert.equal(
    sessionIdentity({ planId: "plan-1", weekPos: 0, dayPos: 0, sessionPos: 0, day, session: {} }),
    "plan-1|w0|d0|s0",
  );
  assert.equal(
    sessionIdentity({
      planId: "plan-1",
      weekPos: 0,
      dayPos: 0,
      sessionPos: 0,
      day,
      session: { session_id: "abc" },
    }),
    "plan-1|2026-06-19|abc",
  );
});
