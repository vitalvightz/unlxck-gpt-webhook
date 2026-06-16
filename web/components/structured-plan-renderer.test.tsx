import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { BlockCard, StructuredPlanRenderer } from "./structured-plan-renderer";
import type { StructuredPlan } from "@/lib/types";

function countOccurrences(text: string, needle: string): number {
  return text.split(needle).length - 1;
}

test("structured renderer uses one session card and hides detail blocks until expanded", () => {
  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    weeks: [
      {
        week_id: "wk-1",
        week_index: 1,
        phase_label: "TAPER",
        days: [
          {
            date: "2026-06-15",
            countdown_label: "D-19",
            day_type: "moderate",
            today_card: {
              headline: "Morning intro duplicate",
              readiness_status: "train_as_planned",
              mindset_anchor: {
                intent: "Duplicate intro intent",
                focus_cue: "Duplicate intro focus",
              },
            },
            sessions: [
              {
                session_id: "ses-1",
                session_type: "mixed",
                title: "Freshness Reset",
                objective: "Restore freshness without adding load.",
                primary_stressor: "skill_priority",
                cns_demand: "low",
                impact_level: "low",
                mindset_anchor: {
                  intent: "Stay loose",
                  focus_cue: "Clean rhythm",
                  reset_cue: "Do not render reset",
                  confidence_anchor: "Do not render anchor",
                  context: "Taper freshness day",
                },
                blocks: [{ block_id: "blk-1", display_name: "Breathing reset" }],
              },
            ],
          },
        ],
      },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} />);

  assert.equal(countOccurrences(html, "Freshness Reset"), 1);
  assert.equal(html.includes("Morning intro duplicate"), false);
  assert.equal(html.includes("Duplicate intro intent"), false);
  assert.equal(html.includes("Breathing reset"), false);
  assert.equal(html.includes("Stressor"), true);
  assert.equal(html.includes("Skill Priority"), true);
  assert.equal(html.includes("CNS"), true);
  assert.equal(html.includes("Show 1 block"), true);
  assert.equal(html.includes("Context"), true);
  assert.equal(html.includes("Taper freshness day"), true);
  assert.equal(html.includes("Do not render reset"), false);
  assert.equal(html.includes("Do not render anchor"), false);
});

test("session card falls back to the day card mindset when the session has none", () => {
  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    weeks: [
      {
        week_id: "wk-1",
        week_index: 1,
        phase_label: "SPP",
        days: [
          {
            date: "2026-06-15",
            countdown_label: "D-19",
            day_type: "hard_spar",
            today_card: {
              readiness_status: "train_as_planned",
              mindset_anchor: {
                intent: "Day card mindset intent",
                focus_cue: "Day card focus cue",
              },
            },
            sessions: [
              {
                session_id: "ses-1",
                session_type: "sparring",
                title: "Hard sparring",
                // No session-level mindset_anchor: the day card should fill in.
                blocks: [{ block_id: "blk-1", display_name: "Live rounds" }],
              },
            ],
          },
        ],
      },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} />);

  assert.equal(html.includes("Day card mindset intent"), true);
  assert.equal(html.includes("Day card focus cue"), true);
});

test("block card surfaces detail tags for expanded session scanning", () => {
  const html = renderToStaticMarkup(
    <BlockCard
      block={{
        block_id: "blk-2",
        display_name: "Medicine ball wall shot",
        block_type: "strength",
        category: "power",
        intensity: "fight rhythm",
        energy_system: "alactic",
        impact_level: "low",
      }}
    />,
  );

  assert.equal(html.includes("Medicine ball wall shot"), true);
  assert.equal(html.includes("Strength"), true);
  assert.equal(html.includes("Power"), true);
  assert.equal(html.includes("Fight Rhythm"), true);
  assert.equal(html.includes("Alactic"), true);
  assert.equal(html.includes("Low"), true);
});
