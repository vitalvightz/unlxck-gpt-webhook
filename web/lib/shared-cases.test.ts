import test from "node:test";
import assert from "node:assert/strict";

import openPlanWeeks from "../../shared/cases/open-plan-weeks.json";
import performanceFocusCases from "../../shared/cases/performance-focus-caps.json";
import primarySessionCases from "../../shared/cases/primary-session.json";
import rehabMatchTerms from "../../shared/cases/rehab-match-terms.json";

import { primarySessionOf, resolveOpenPlanWeekNumber } from "@/lib/camp-map";
import { getPerformanceFocusCap, validatePerformanceFocusSelections } from "@/lib/performance-focus-cap";
import { normalizeRehabText } from "@/lib/rehab-label";
import type { StructuredDay, StructuredPlan } from "@/lib/types";

// shared/cases/*.json hold inputs with the backend's answers
// (tests/test_shared_cases.py checks the backend against the same files). The
// web app re-implements these rules for rendering, so it must give the same
// answers.

test("rehab match terms normalize like the backend", () => {
  for (const { input, expected } of rehabMatchTerms.cases) {
    assert.equal(normalizeRehabText(input), expected, JSON.stringify(input));
  }
});

test("the open-plan week matches the backend projection", () => {
  const fourWeekPlan = { weeks: [{}, {}, {}, {}] } as unknown as StructuredPlan;
  for (const entry of openPlanWeeks.cases) {
    const [year, month, day] = entry.current_training_day.split("-").map(Number);
    const today = new Date(year, month - 1, day);
    assert.equal(
      resolveOpenPlanWeekNumber(fourWeekPlan, today, { createdAt: entry.created_at }),
      entry.expected_week_number,
      `${entry.created_at} on ${entry.current_training_day}`,
    );
  }
});

test("the primary session matches the backend", () => {
  for (const { sessions, expected_index } of primarySessionCases.cases) {
    const day = { sessions } as unknown as StructuredDay;
    assert.equal(primarySessionOf(day), sessions[expected_index], JSON.stringify(sessions.map((s) => s.title)));
  }
});

test("focus caps match the backend", () => {
  for (const entry of performanceFocusCases.cases.caps) {
    const cap = getPerformanceFocusCap(entry.fight_date, { now: new Date(entry.now), timeZone: entry.time_zone });
    const label = `${entry.fight_date} at ${entry.now} ${entry.time_zone}`;
    if (entry.expected === null) {
      assert.equal(cap, null, label);
      continue;
    }
    assert.ok(cap, label);
    assert.deepEqual(
      {
        open_plan: cap.daysUntilFight === Number.POSITIVE_INFINITY,
        days_until_fight: Number.isFinite(cap.daysUntilFight) ? cap.daysUntilFight : null,
        weeks_out: Number.isFinite(cap.weeksOut) ? cap.weeksOut : null,
        max_selections: cap.maxSelections,
        window_label: cap.windowLabel,
      },
      entry.expected,
      label,
    );
  }
});

test("focus-cap validation messages match the backend", () => {
  for (const entry of performanceFocusCases.cases.validations) {
    const result = validatePerformanceFocusSelections(
      entry.fight_date,
      { keyGoals: Array(entry.key_goals).fill("g"), weakAreas: Array(entry.weak_areas).fill("w") },
      { now: new Date(entry.now), timeZone: entry.time_zone },
    );
    assert.equal(result.excessSelections, entry.expected_excess);
    assert.equal(result.errorMessage, entry.expected_message);
  }
});
