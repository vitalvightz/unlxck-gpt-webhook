import test from "node:test";
import assert from "node:assert/strict";

import {
  cleanText,
  formatBlockLoad,
  formatMeasured,
  getBlocks,
  getCoachingCues,
  getDays,
  getDisplayableRedFlags,
  getMindsetLines,
  getSessions,
  getStringList,
  getWeeks,
  hasNutrition,
  isTimeLikeReps,
  selectBlockMetric,
  shouldRenderStructuredPlan,
  shouldShowRest,
} from "./structured-plan.ts";

function validPlan() {
  return {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    athlete_context: { sport_profile: "amateur boxer" },
    red_flag_rules: [
      { rule_id: "r1", severity: "red", display_text: "Sharp pain — stop and report.", action: "Notify coach." },
    ],
    nutrition: { summary: "Fuel around sessions.", daily_focus: "Protein + carbs." },
    weeks: [
      {
        week_id: "wk-1",
        week_index: 1,
        phase_label: "SPP",
        week_goal: "Power",
        days: [
          {
            date: "2026-05-29",
            day_type: "high",
            countdown_label: "D-15",
            today_card: {
              headline: "Power day",
              readiness_status: "train_as_planned",
              mindset_anchor: { intent: "Move fast", focus_cue: "Drive the floor", reset_cue: "Breathe out" },
            },
            sessions: [
              {
                session_id: "ses-1",
                session_type: "strength_power",
                title: "Power Transfer",
                objective: "Raise punch speed.",
                mindset_anchor: { intent: "Snap", focus_cue: "Fast hands", reset_cue: "Reset stance" },
                blocks: [
                  {
                    block_id: "blk-1",
                    block_type: "strength",
                    display_name: "Back Squat",
                    sets: 4,
                    reps: "4-6",
                    load: { method: "percentage", value: 85, unit: "percent", display: "85% 1RM" },
                    rest: { value: 180, unit: "seconds" },
                  },
                ],
              },
            ],
          },
        ],
      },
    ],
    raw_markdown_fallback: "# Fight Camp\n...",
  };
}

// --- render decision: structured vs plan_text fallback ----------------------

test("renders plan_text (no structured) when structured_plan is null", () => {
  assert.equal(shouldRenderStructuredPlan({ structured_plan: null }), false);
  assert.equal(shouldRenderStructuredPlan({ structured_plan: undefined }), false);
  assert.equal(shouldRenderStructuredPlan(null), false);
  assert.equal(shouldRenderStructuredPlan(undefined), false);
});

test("renders structured_plan when present with weeks", () => {
  assert.equal(shouldRenderStructuredPlan({ structured_plan: validPlan() }), true);
});

test("falls back to plan_text when structured_plan is malformed", () => {
  // Wrong types / no usable weeks must not render the structured UI.
  assert.equal(shouldRenderStructuredPlan({ structured_plan: {} as never }), false);
  assert.equal(shouldRenderStructuredPlan({ structured_plan: { weeks: [] } as never }), false);
  assert.equal(shouldRenderStructuredPlan({ structured_plan: { weeks: "nope" } as never }), false);
  assert.equal(shouldRenderStructuredPlan({ structured_plan: "raw text" as never }), false);
  assert.equal(shouldRenderStructuredPlan({ structured_plan: [] as never }), false);
});

// --- defensive selectors: never crash on partial data -----------------------

test("selectors return safe empties on missing/partial fields", () => {
  assert.deepEqual(getWeeks(null), []);
  assert.deepEqual(getWeeks({} as never), []);
  assert.deepEqual(getDays(undefined), []);
  assert.deepEqual(getSessions({ sessions: null } as never), []);
  assert.deepEqual(getBlocks({} as never), []);
  assert.deepEqual(getCoachingCues({} as never), []);
  assert.deepEqual(getMindsetLines(undefined), []);
  // A week/day/session with null nested arrays does not throw.
  const week = getWeeks({ structured_plan: validPlan() } as never);
  assert.equal(week.length, 0); // wrong-shaped input -> empty, no crash
});

// --- field display rules ----------------------------------------------------

test("hides 0-second rest, shows positive rest", () => {
  assert.equal(shouldShowRest({ value: 0, unit: "seconds" }), false);
  assert.equal(shouldShowRest({ value: 180, unit: "seconds" }), true);
  assert.equal(shouldShowRest(null), false);
  assert.equal(shouldShowRest({} as never), false);
});

test("hides null / empty / meaningless loads, keeps real display", () => {
  assert.equal(formatBlockLoad(null), null);
  assert.equal(formatBlockLoad({} as never), null);
  assert.equal(formatBlockLoad({ display: "" }), null);
  assert.equal(formatBlockLoad({ display: "   " }), null);
  assert.equal(formatBlockLoad({ display: "n/a" }), null);
  assert.equal(formatBlockLoad({ display: "0" }), null);
  assert.equal(formatBlockLoad({ method: "percentage", value: 85, unit: "percent", display: "85% 1RM" }), "85% 1RM");
});

test("cleanText hides blank values", () => {
  assert.equal(cleanText(null), null);
  assert.equal(cleanText("  "), null);
  assert.equal(cleanText(42 as never), null);
  assert.equal(cleanText(" squat "), "squat");
});

test("formatMeasured renders value + unit, or null", () => {
  assert.equal(formatMeasured({ value: 45, unit: "minutes" }), "45 minutes");
  assert.equal(formatMeasured({ value: 30, unit: null }), "30");
  assert.equal(formatMeasured(null), null);
  assert.equal(formatMeasured({ unit: "minutes" } as never), null);
});

test("prefers duration over reps when reps looks like a time string", () => {
  assert.equal(isTimeLikeReps("5-6 min"), true);
  assert.equal(isTimeLikeReps("30s"), true);
  assert.equal(isTimeLikeReps("4-6"), false);

  const timeReps = selectBlockMetric({
    reps: "5-6 min",
    duration: { value: 6, unit: "minutes" },
  } as never);
  assert.deepEqual(timeReps, [{ label: "Duration", value: "6 minutes" }]);

  const realReps = selectBlockMetric({ sets: 4, reps: "4-6" } as never);
  assert.deepEqual(realReps, [{ label: "Volume", value: "4 × 4-6" }]);

  assert.deepEqual(selectBlockMetric({} as never), []);
  assert.deepEqual(selectBlockMetric(null), []);
});

test("isTimeLikeReps treats bare metres as NOT time (metres/minutes ambiguity)", () => {
  // "5 m" / "5m" reps mean metres, not minutes — must not be coerced to duration.
  assert.equal(isTimeLikeReps("5 m"), false);
  assert.equal(isTimeLikeReps("400m"), false);
  // Unambiguous time units still match.
  assert.equal(isTimeLikeReps("2 min"), true);
  assert.equal(isTimeLikeReps("90 seconds"), true);
});

test("selectBlockMetric renders distance and rounds for conditioning blocks", () => {
  assert.deepEqual(selectBlockMetric({ distance: { value: 400, unit: "meters" } } as never), [
    { label: "Distance", value: "400 meters" },
  ]);
  assert.deepEqual(selectBlockMetric({ rounds: 8 } as never), [
    { label: "Rounds", value: "8" },
  ]);
  // Zero/negative rounds are hidden.
  assert.deepEqual(selectBlockMetric({ rounds: 0 } as never), []);
});

test("selectBlockMetric combines duration, distance, and rounds in order", () => {
  const metrics = selectBlockMetric({
    reps: "30s",
    duration: { value: 5, unit: "minutes" },
    distance: { value: 400, unit: "meters" },
    rounds: 8,
  } as never);
  assert.deepEqual(metrics, [
    { label: "Duration", value: "5 minutes" },
    { label: "Distance", value: "400 meters" },
    { label: "Rounds", value: "8" },
  ]);
});

// --- content presence: blocks / mindset / nutrition / red flags -------------

test("extracts session blocks from a valid plan", () => {
  const plan = validPlan();
  const blocks = getBlocks(getSessions(getDays(getWeeks(plan)[0])[0])[0]);
  assert.equal(blocks.length, 1);
  assert.equal(blocks[0].display_name, "Back Squat");
});

test("extracts mindset anchor lines", () => {
  const session = getSessions(getDays(getWeeks(validPlan())[0])[0])[0];
  const lines = getMindsetLines(session.mindset_anchor);
  assert.equal(lines.length, 3);
  assert.deepEqual(
    lines.map((line) => line.label),
    ["Intent", "Focus", "Reset"],
  );
});

test("detects nutrition when present, absent when empty", () => {
  assert.equal(hasNutrition(validPlan()), true);
  assert.equal(hasNutrition({ nutrition: {} } as never), false);
  assert.equal(hasNutrition({} as never), false);
});

test("surfaces displayable red flags only", () => {
  assert.equal(getDisplayableRedFlags(validPlan()).length, 1);
  assert.equal(getDisplayableRedFlags({ red_flag_rules: [{ rule_id: "x" }] } as never).length, 0);
  assert.equal(getDisplayableRedFlags({} as never).length, 0);
});

test("getStringList cleans, drops blanks, and tolerates null", () => {
  assert.deepEqual(getStringList(["Brace hard", "  ", "Knees out"]), ["Brace hard", "Knees out"]);
  assert.deepEqual(getStringList(null), []);
  assert.deepEqual(getStringList(undefined), []);
  assert.deepEqual(getStringList([]), []);
});

test("getMindsetLines includes confidence_anchor when present", () => {
  const lines = getMindsetLines({
    intent: "Move fast",
    focus_cue: "Drive",
    reset_cue: "Reset",
    confidence_anchor: "Banked the work",
  });
  assert.deepEqual(
    lines.map((l) => l.label),
    ["Intent", "Focus", "Reset", "Anchor"],
  );
  // Empty anchor object yields no lines (renderer hides it).
  assert.deepEqual(getMindsetLines({}), []);
  assert.deepEqual(getMindsetLines(null), []);
});
