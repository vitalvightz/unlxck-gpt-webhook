// What the athlete actually sees when the deterministic fallback IS the card.
//
// Production commonly stores structured_plan = NULL, so the card rendered here
// is the one api/structured_plan_deterministic_fallback.py assembles from the
// planning brief. These tests render the real renderer over that payload shape.
import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { StructuredPlanRenderer } from "./structured-plan-renderer";
import { dayCompletion } from "@/lib/camp-map";
import { getPhysicalSessions, isZeroLoadSupportSession } from "@/lib/structured-plan";
import type { StructuredDay, StructuredPlan, StructuredSession } from "@/lib/types";

/** The shape api/structured_plan_deterministic_fallback._session emits. */
const jointPrep: StructuredSession = {
  session_id: "deterministic-10-joint_prep-0",
  session_type: "rehab",
  title: "Joint Prep",
  objective:
    "Neck CARs, shoulder CARs, wrist circles, hip circles, and ankle rocks. Stay smooth and pain-free.",
  blocks: [],
};

const breathingReset: StructuredSession = {
  session_id: "deterministic-9-breathing_reset-0",
  session_type: "recovery",
  title: "Breathing Reset",
  objective: "Nasal breathing if comfortable. Use a 4-6 second inhale and 6-8 second exhale.",
  blocks: [],
};

const pressureStepCut: StructuredSession = {
  session_id: "deterministic-9-footwork_walkthrough-0",
  session_type: "skill",
  title: "Pressure Step-Cut Reset",
  objective:
    "Read the opponent's exit lane, cut it off, and reset the base before punching.",
  blocks: [
    {
      block_id: "deterministic-9-footwork_walkthrough-display",
      block_type: "skill",
      display_name: "Pressure Step-Cut Reset",
      order_index: 0,
      why_today: "Read the opponent's exit lane, cut it off, and reset the base before punching.",
      coaching_cues: [
        "2 sets x 4 clean reactions each direction, full stance reset between reps. Rest: 75 sec between sets.",
        "Cue: React to a partner exit, coach direction call, or random left/right visual cue.",
        "Cue Method: Have your partner feed the cue at random timing; reset fully between reps.",
        "Side / Stance: Start in your orthodox stance and work both directions evenly.",
      ],
      stop_rules: [
        "Stop the set when the lane read, braking control, or stance reset loses quality.",
      ],
    },
  ],
};

const visualisation: StructuredSession = {
  session_id: "deterministic-9-neural_visualization-0",
  session_type: "skill",
  title: "Neural Visualization",
  objective: "Rehearse the opening exchange so the first minute is familiar.",
  blocks: [],
};

function planWith(days: StructuredDay[]): StructuredPlan {
  return {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    weeks: [{ week_id: "wk-1", week_index: 1, phase_label: "TAPER", days }],
  };
}

const day = (countdown: string, date: string, sessions: StructuredSession[]): StructuredDay => ({
  date,
  countdown_label: countdown,
  day_type: "low",
  sessions,
});

function render(plan: StructuredPlan): string {
  return renderToStaticMarkup(
    <StructuredPlanRenderer plan={plan} today={new Date("2026-10-06T12:00:00")} />,
  );
}

test("a blockless instruction card reads as the instruction, not as a Why", () => {
  const markup = render(planWith([day("D-10", "2026-10-05", [jointPrep])]));

  assert.match(markup, /Joint Prep/);
  assert.match(markup, /Neck CARs, shoulder CARs/);
  // The kicker labels a rationale. With no blocks the objective IS the
  // prescription, so it must not be introduced as "Why".
  assert.equal(markup.includes("sp-session-why-label"), false);
  // And it is not recovery-tagged physical support.
  assert.equal(markup.includes(">Recovery<"), false);
});

test("a parsed drill card keeps Why, prescription, cues and its stop rule", () => {
  const markup = render(planWith([day("D-9", "2026-10-06", [pressureStepCut])]));

  // The Why kicker is correct here: there IS work below for it to explain.
  assert.match(markup, /sp-session-why-label/);
  assert.match(markup, /Read the opponent&#x27;s exit lane/);
  // No "WHY Why:" duplication of the source label.
  assert.equal(/Why<\/span>\s*Why:/.test(markup), false);
  assert.match(markup, /2 sets x 4 clean reactions each direction/);
  assert.match(markup, /Rest: 75 sec between sets/);
  assert.match(markup, /Cue Method:/);
  assert.match(markup, /Side \/ Stance:/);
  // Quality Stop renders under the stop-rule label, never as "Progress".
  assert.match(markup, /Stop rule/);
  assert.match(markup, /braking control, or stance reset loses quality/);
  assert.equal(markup.includes("Quality Stop"), false);
  assert.match(markup, /Skill/);
});

test("same-day support and physical work coexist, counted once", () => {
  const d9 = day("D-9", "2026-10-06", [breathingReset, pressureStepCut, visualisation]);
  const markup = render(planWith([d9]));

  assert.match(markup, /Breathing Reset/);
  assert.match(markup, /Pressure Step-Cut Reset/);
  assert.match(markup, /Neural Visualization/);
  assert.equal(markup.includes("cm-rest-day"), false);

  assert.equal(isZeroLoadSupportSession(breathingReset), true);
  assert.equal(isZeroLoadSupportSession(visualisation), true);
  assert.equal(isZeroLoadSupportSession(pressureStepCut), false);
  assert.equal(isZeroLoadSupportSession(jointPrep), false);
  assert.deepEqual(
    getPhysicalSessions(d9).map((session) => session.title),
    ["Pressure Step-Cut Reset"],
  );
  assert.equal(dayCompletion(d9).total, 1);
});

test("a day with no sessions still renders as rest", () => {
  const markup = render(
    planWith([
      day("D-9", "2026-10-06", [pressureStepCut]),
      { date: "2026-10-08", countdown_label: "D-7", day_type: "rest", sessions: [] },
    ]),
  );

  assert.match(markup, /cm-rest-day/);
});
