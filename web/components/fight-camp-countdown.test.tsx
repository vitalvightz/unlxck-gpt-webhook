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
  assert.match(html, /Next up/);
  assert.match(html, /Taper begins in 5 days/);
  assert.equal((html.match(/fight-countdown-segment"/g) ?? []).length, 4);
  assert.equal((html.match(/data-current="true"/g) ?? []).length, 2); // segment + legend
  assert.match(html, /role="progressbar"/);
  assert.match(html, /aria-label="Fight camp countdown, 17 days to fight night, Week 2 of 4, SPP"/);
});

test("Today countdown is a compact row with the next milestone", () => {
  const html = renderToStaticMarkup(
    <FightCampCountdown plan={plan()} trainingDay={new Date(2026, 5, 26)} variant="today" />,
  );
  assert.match(html, /data-variant="today"/);
  assert.match(html, /1 day <span class="fight-countdown-compact-target">to fight night/);
  assert.match(html, /Next: Fight night tomorrow/);
  assert.doesNotMatch(html, /Banked/);
});

test("Countdown renders nothing without a plan", () => {
  assert.equal(renderToStaticMarkup(<FightCampCountdown plan={null} trainingDay={new Date()} />), "");
});
