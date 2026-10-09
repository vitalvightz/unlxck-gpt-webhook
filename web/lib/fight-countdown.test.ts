import test from "node:test";
import assert from "node:assert/strict";

import { getFightCountdown } from "./fight-countdown.ts";
import type { StructuredPlan } from "@/lib/types";

// 4 Mon-Sun weeks from Mon 2026-06-01; fight Sat 2026-06-27.
function plan(phases = ["GPP", "SPP", "TAPER", "FIGHT_WEEK"]): StructuredPlan {
  return {
    weeks: phases.map((phase, index) => {
      const start = new Date(Date.UTC(2026, 5, 1 + index * 7));
      const end = new Date(Date.UTC(2026, 5, 7 + index * 7));
      return {
        week_index: index + 1,
        phase_label: phase,
        start_date: start.toISOString().slice(0, 10),
        end_date: end.toISOString().slice(0, 10),
      };
    }),
  };
}

test("mid-camp: days out, week, phase, progress and the next phase change", () => {
  const countdown = getFightCountdown({
    fightDate: "2026-06-27",
    trainingDay: "2026-06-10",
    phase: "SPP",
    plan: plan(),
  });
  assert.ok(countdown);
  assert.equal(countdown.daysOut, 17);
  assert.equal(countdown.weekLabel, "Week 2 of 4");
  assert.equal(countdown.phaseLabel, "Specific prep");
  assert.equal(countdown.nextLabel, "Taper starts in 5 days");
  assert.ok(countdown.pct !== null && countdown.pct > 30 && countdown.pct < 40);
});

test("counts down to fight night even when the plan JSON has no fight date", () => {
  // The bug behind "30 days left in this block": the fight date lives on the
  // server's active plan, not in structured_plan.event_context.
  const countdown = getFightCountdown({
    fightDate: "2026-06-27",
    trainingDay: "2026-05-28",
    phase: "GPP",
    plan: { ...plan(), event_context: null },
  });
  assert.equal(countdown?.daysOut, 30);
  assert.equal(countdown?.phaseLabel, "General prep");
});

test("fight day reads D-0 with no next line; after the fight it hides", () => {
  const fightDay = getFightCountdown({ fightDate: "2026-06-27", trainingDay: "2026-06-27", plan: plan() });
  assert.equal(fightDay?.daysOut, 0);
  assert.equal(fightDay?.nextLabel, null);
  assert.equal(fightDay?.pct, 100);
  assert.equal(getFightCountdown({ fightDate: "2026-06-27", trainingDay: "2026-06-28", plan: plan() }), null);
});

test("open plans and bad dates get no countdown", () => {
  assert.equal(getFightCountdown({ fightDate: null, trainingDay: "2026-06-10", plan: plan() }), null);
  assert.equal(getFightCountdown({ fightDate: "", trainingDay: "2026-06-10" }), null);
  assert.equal(getFightCountdown({ fightDate: "2026-06-27", trainingDay: null }), null);
  assert.equal(getFightCountdown({ fightDate: "soon", trainingDay: "2026-06-10" }), null);
});

test("falls back to fight night when no phase change remains", () => {
  const countdown = getFightCountdown({ fightDate: "2026-06-27", trainingDay: "2026-06-23", plan: plan() });
  assert.equal(countdown?.phaseLabel, "Fight week");
  assert.equal(countdown?.nextLabel, "Fight night in 4 days");
  assert.equal(
    getFightCountdown({ fightDate: "2026-06-27", trainingDay: "2026-06-26", plan: plan() })?.nextLabel,
    "Fight night tomorrow",
  );
});

test("works without a structured plan: countdown only, no bar or week", () => {
  const countdown = getFightCountdown({ fightDate: "2026-06-27", trainingDay: "2026-06-10", phase: "SPP" });
  assert.equal(countdown?.daysOut, 17);
  assert.equal(countdown?.pct, null);
  assert.equal(countdown?.weekLabel, null);
  assert.equal(countdown?.phaseLabel, "Specific prep");
  assert.equal(countdown?.nextLabel, "Fight night in 17 days");
});
