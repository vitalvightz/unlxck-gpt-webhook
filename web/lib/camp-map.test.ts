import test from "node:test";
import assert from "node:assert/strict";

import {
  dayCompletion,
  deriveCountdownLabel,
  findDayByISO,
  getReadinessStrip,
  resolvePlanProgress,
  toISODate,
  weekCompletion,
  weekLoadProxy,
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
            today_card: { headline: "Train as planned", readiness_status: "train_as_planned" },
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

test("getReadinessStrip surfaces today call, focus, risk and load", () => {
  const plan = campPlan();
  const currentDay = findDayByISO(plan, "2026-06-19");
  const strip = getReadinessStrip(plan, currentDay, plan.weeks![0]);
  assert.equal(strip.todayCall, "Train as planned");
  assert.equal(strip.focus, "Convert strength into speed.");
  assert.equal(strip.risk, "Stop if Achilles pain ≥ 6/10.");
  assert.equal(strip.load, "Moderate");
});

test("getReadinessStrip degrades gracefully with no current day", () => {
  const plan = campPlan();
  const strip = getReadinessStrip(plan, null, plan.weeks![1]);
  assert.equal(strip.todayCall, null);
  assert.equal(strip.focus, "Sharpen and freshen.");
  assert.equal(strip.risk, "Stop if Achilles pain ≥ 6/10.");
  assert.equal(strip.load, null);
});
