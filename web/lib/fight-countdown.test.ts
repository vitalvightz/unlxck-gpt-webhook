import test from "node:test";
import assert from "node:assert/strict";

import { getFightCountdown } from "./fight-countdown.ts";
import type { StructuredDay, StructuredPlan } from "@/lib/types";

const isoUtc = (y: number, m: number, d: number) => new Date(Date.UTC(y, m, d)).toISOString().slice(0, 10);

function days(startDay: number, count: number, phase: string | ((index: number) => string)): StructuredDay[] {
  return Array.from({ length: count }, (_, index) => ({
    date: isoUtc(2026, 5, startDay + index),
    phase_label: typeof phase === "string" ? phase : phase(index),
    day_type: "moderate",
    sessions: [],
  }));
}

// 4 Mon-Sun weeks from Mon 2026-06-01; fight Sat 2026-06-27.
function plan(phases = ["GPP", "SPP", "TAPER", "FIGHT_WEEK"]): StructuredPlan {
  return {
    weeks: phases.map((phase, index) => ({
      week_index: index + 1,
      phase_label: phase,
      start_date: isoUtc(2026, 5, 1 + index * 7),
      end_date: isoUtc(2026, 5, 7 + index * 7),
      days: days(1 + index * 7, 7, phase),
    })),
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
  assert.equal(countdown.campDays, 26);
  assert.ok(countdown.pct !== null && countdown.pct > 30 && countdown.pct < 40);
});

test("finds a phase change that happens mid-week", () => {
  // Week 3 is labelled TAPER as a week, but its days switch from TAPER to
  // FIGHT_WEEK on Fri 2026-06-19 — the week label alone would miss it.
  const camp = plan(["GPP", "SPP", "TAPER"]);
  camp.weeks![2].days = days(15, 7, (index) => (index < 4 ? "TAPER" : "FIGHT_WEEK"));
  const countdown = getFightCountdown({ fightDate: "2026-06-21", trainingDay: "2026-06-16", plan: camp });
  assert.equal(countdown?.phaseLabel, "Taper");
  assert.equal(countdown?.nextLabel, "Fight week starts in 3 days");
});

test("numbers weeks like the plan page when one block spans several calendar weeks", () => {
  // A late-fight plan shipped as ONE week object covering three calendar
  // weeks; getWeeks() splits it into Mon-Sun weeks.
  const lateFight: StructuredPlan = {
    weeks: [
      {
        week_index: 1,
        phase_label: "SPP",
        start_date: "2026-06-01",
        end_date: "2026-06-20",
        days: days(1, 20, (index) => (index < 12 ? "SPP" : index < 17 ? "TAPER" : "FIGHT_WEEK")),
      },
    ],
  };
  const countdown = getFightCountdown({ fightDate: "2026-06-20", trainingDay: "2026-06-09", plan: lateFight });
  assert.equal(countdown?.weekLabel, "Week 2 of 3");
  assert.equal(countdown?.nextLabel, "Taper starts in 4 days");
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
  // Impossible dates are rejected, not rolled into the next month.
  assert.equal(getFightCountdown({ fightDate: "2026-02-31", trainingDay: "2026-02-10" }), null);
  assert.equal(getFightCountdown({ fightDate: "2026-06-27", trainingDay: "2026-06-31" }), null);
});

test("ignores impossible dates inside the plan calendar", () => {
  const camp = plan();
  camp.weeks![0].start_date = "2026-05-32";
  camp.weeks![0].days![0].date = "2026-05-32";
  const countdown = getFightCountdown({ fightDate: "2026-06-27", trainingDay: "2026-06-10", plan: camp });
  // Camp start falls back to the next real date (Tue 2026-06-02).
  assert.equal(countdown?.campDays, 25);
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
  assert.equal(countdown?.campDays, null);
  assert.equal(countdown?.weekLabel, null);
  assert.equal(countdown?.phaseLabel, "Specific prep");
  assert.equal(countdown?.nextLabel, "Fight night in 17 days");
});
