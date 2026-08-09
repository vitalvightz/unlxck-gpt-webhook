import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { StructuredPlanRenderer } from "./structured-plan-renderer";
import type { StructuredPlan } from "@/lib/types";

function countOccurrences(text: string, needle: string): number {
  return text.split(needle).length - 1;
}

test("reported D-13 band primer keeps exact dose and one non-duplicated stop rule", () => {
  const raw = `Left shoulder surface abrasion. No open wound or infection reported. Keep the area clean and covered during training; stop and seek care if bleeding, spreading redness, or increased pain.
- Target weight is not set, so weight-cut guidance is not applied.

D-13 (Monday): Neural speed touch
- Band-Resisted Jab-Cross Primer — 2-3 sets x 6 punches per set (focus on intent and snap), full recovery between sets 90-120 sec, RPE 6-7.
  Easier: do 1-2 sets of unresisted shadow jab-cross at the same tempo.
  Stop: any sharp pain at the left shoulder, wound irritation, or if speed degrades and form breaks.`;

  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    raw_markdown_fallback: raw,
    plan_notes: [
      {
        category: "injury",
        label: "Left shoulder abrasion",
        text: "Left shoulder surface abrasion. No open wound or infection reported. Keep the area clean and covered during training; stop and seek care if bleeding, spreading redness, or increased pain.",
      },
    ],
    red_flag_rules: [
      {
        rule_id: "shoulder-surface",
        severity: "red",
        when: "during_session",
        display_text: "Stop and seek care for bleeding, spreading redness, or increased pain.",
        action: "Seek care if these signs appear.",
      },
    ],
    weeks: [
      {
        week_id: "wk-1",
        week_index: 1,
        phase_label: "TAPER",
        days: [
          {
            date: "2026-08-10",
            countdown_label: "D-13",
            day_type: "low",
            sessions: [
              {
                session_id: "neural-speed",
                session_type: "skill",
                title: "Neural speed touch",
                blocks: [
                  {
                    block_id: "band-primer",
                    block_type: "skill",
                    display_name: "Band-Resisted Jab-Cross Primer",
                    sets: 2,
                    reps: "6 punches per set",
                    effort: { method: "RPE", value: 6.5 },
                    regression_options: [
                      "Do 1-2 sets of unresisted shadow jab-cross at the same tempo.",
                    ],
                    stop_rules: [
                      "Any sharp pain at the left shoulder",
                      "Wound irritation",
                      "If speed degrades and form breaks",
                    ],
                  },
                ],
              },
            ],
          },
        ],
      },
    ],
  } as StructuredPlan;

  const html = renderToStaticMarkup(
    <StructuredPlanRenderer plan={plan} today={new Date(2026, 7, 10)} />,
  );

  assert.equal(html.includes("2-3 × 6 punches"), true);
  assert.equal(html.includes("RPE 6-7"), true);
  assert.equal(html.includes("RPE 6.5"), false);

  assert.equal(countOccurrences(html, ">Stop rule</span>"), 1);
  assert.equal(html.includes("If speed degrades and form breaks"), true);
  assert.equal(html.includes("Any sharp pain at the left shoulder"), false);
  assert.equal(html.includes(">Wound irritation<"), false);

  // Active Notes keeps condition/management while Safety Priority owns escalation.
  assert.equal(html.includes("Keep the area clean and covered during training"), true);
  assert.equal(countOccurrences(html, "stop and seek care if bleeding"), 0);
  assert.equal(countOccurrences(html, "Stop and seek care for bleeding"), 1);
});
