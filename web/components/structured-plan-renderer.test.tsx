import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { StructuredPlanRenderer } from "./structured-plan-renderer";
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
  assert.equal(html.includes("MORE"), true);
  assert.equal(html.includes("Context"), true);
  assert.equal(html.includes("Taper freshness day"), true);
  assert.equal(html.includes("Do not render reset"), false);
  assert.equal(html.includes("Do not render anchor"), false);
});

test("renders a coach-led / sparring day with no app blocks as its own card", () => {
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
            date: "2026-06-20",
            countdown_label: "D-16",
            day_type: "high",
            today_card: { headline: "Coach-led boxing — technical only" },
            sessions: [],
          },
          {
            date: "2026-06-21",
            countdown_label: "D-15",
            day_type: "rest",
            today_card: {},
            sessions: [],
          },
        ],
      },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} />);

  // The coach-led day surfaces its headline and the coach note instead of
  // collapsing into a rest day.
  assert.equal(html.includes("Coach-led boxing — technical only"), true);
  assert.equal(html.includes("train with your coach"), true);
  assert.equal(html.includes("sp-day-card-technical"), true);
  // The genuine rest day still reads as a rest day exactly once.
  assert.equal(countOccurrences(html, "Rest day."), 1);
});

test("renders plan-level active notes as a standalone card", () => {
  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    plan_notes: [
      { category: "weight_cut", label: "Active weight cut", text: "~5.7% target — protect freshness." },
      { category: "injury", text: "Small cut above the elbow — keep covered and dry." },
    ],
    weeks: [
      {
        week_id: "wk-1",
        week_index: 1,
        phase_label: "GPP",
        days: [],
      },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} />);

  assert.equal(html.includes("Active notes"), true);
  assert.equal(html.includes("~5.7% target — protect freshness."), true);
  assert.equal(html.includes("Small cut above the elbow — keep covered and dry."), true);
  // Weight-cut / injury notes get the accent class.
  assert.equal(html.includes("sp-note-weight_cut"), true);
  assert.equal(html.includes("sp-note-injury"), true);
});
