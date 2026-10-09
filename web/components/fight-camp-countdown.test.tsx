import "./test-dom";

import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { FightCampCountdown } from "./fight-camp-countdown";
import { toISODate } from "../lib/camp-map";
import type { StructuredPlan } from "../lib/types";

function plan(): StructuredPlan {
  const phases = ["GPP", "SPP", "TAPER", "FIGHT_WEEK"];
  return {
    event_context: { fight_date: "2026-06-27" },
    weeks: phases.map((phase, weekIndex) => ({
      week_index: weekIndex + 1,
      phase_label: phase,
      days: Array.from({ length: 7 }, (_, dayIndex) => ({
        date: toISODate(new Date(2026, 5, 1 + weekIndex * 7 + dayIndex)),
        phase_label: phase,
        day_type: "moderate",
        sessions: [],
      })),
    })),
  };
}

test("Overview countdown shows days to fight night, the phase strip and next milestone", () => {
  const html = renderToStaticMarkup(
    <FightCampCountdown plan={plan()} trainingDay={new Date(2026, 5, 10)} variant="overview" />,
  );
  assert.match(html, /fight-countdown-number[^>]*>17</);
  assert.match(html, /days to fight night/);
  assert.match(html, /Week 2 of 4 · SPP/);
  assert.match(html, /Next up<\/span><span class="fight-countdown-stat-value">Taper begins<\/span><span class="fight-countdown-stat-sub">in 5 days/);
  assert.match(html, /fight-countdown-fill" style="width:[\d.]+%"/);
  assert.match(html, /fight-countdown-endcap/);
  assert.equal((html.match(/fight-countdown-divider"/g) ?? []).length, 3);
  assert.match(html, /legend-item" data-current="true"[^>]*>SPP</);
  assert.match(html, />Camp<\/span><span class="fight-countdown-stat-value">\d+%/);
  assert.doesNotMatch(html, /Banked/);
  assert.match(html, /role="progressbar"/);
  assert.match(html, /aria-label="Fight camp countdown, 17 days to fight night, Week 2 of 4, SPP"/);
});

test("Today countdown is a compact row with the next milestone", () => {
  const html = renderToStaticMarkup(
    <FightCampCountdown plan={plan()} trainingDay={new Date(2026, 5, 26)} variant="today" />,
  );
  assert.match(html, /data-variant="today"/);
  assert.match(html, /fight-countdown-gold">1 day<\/span> <span class="fight-countdown-compact-target">to fight night/);
  assert.match(html, /Next<\/span>Fight night<span class="fight-countdown-gold"> tomorrow/);
  assert.doesNotMatch(html, /Banked/);
});

test("Overview countdown shows banked sessions and milestone pins", () => {
  const base = plan();
  base.event_context = { fight_date: "2026-06-27" };
  base.weeks![1].days![2].planning_day_role_keys = ["hard_sparring_day"];
  base.weeks![0].days![0].sessions = [
    { session_id: "s1", title: "Strength", session_type: "strength", blocks: [{ title: "Main", exercises: [{ name: "Squat" }] }] },
  ] as never;
  const html = renderToStaticMarkup(
    <FightCampCountdown
      plan={base}
      trainingDay={new Date(2026, 5, 20)}
      completions={[{ training_day: "2026-06-01", session_id: "s1", status: "done" }] as never}
      variant="overview"
    />,
  );
  assert.match(html, /Banked<\/span><span class="fight-countdown-stat-value">1<span class="fight-countdown-stat-of"> \/ 1/);
  assert.match(html, /fight-countdown-pin" data-passed="true"/);
});

test("Countdown renders nothing without a plan", () => {
  assert.equal(renderToStaticMarkup(<FightCampCountdown plan={null} trainingDay={new Date()} />), "");
});
