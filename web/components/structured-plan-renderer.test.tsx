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
  assert.equal(html.includes("MORE"), false);
  assert.equal(html.includes("LESS"), false);
  assert.equal(html.includes("Show more (1 block)"), true);
  assert.equal(html.includes("Context"), true);
  assert.equal(html.includes("Taper freshness day"), true);
  assert.equal(html.includes("Do not render reset"), false);
  assert.equal(html.includes("Do not render anchor"), false);
});

test("surfaces rehab summary while keeping full rehab details collapsed", () => {
  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    weeks: [
      {
        week_id: "wk-1",
        week_index: 1,
        phase_label: "GPP",
        days: [
          {
            date: "2026-06-17",
            countdown_label: "D-34",
            day_type: "low",
            sessions: [
              {
                session_id: "ses-1",
                session_type: "conditioning",
                title: "Assault Bike aerobic steady state + rehab",
                blocks: [
                  { block_id: "bike", block_type: "conditioning", display_name: "Easy Assault Bike" },
                  {
                    block_id: "rehab",
                    block_type: "rehab",
                    display_name: "Neutral-Grip Isometric Holds",
                    sets: 2,
                    reps: "12-15 s",
                    coaching_cues: ["Full rest between holds"],
                  },
                ],
              },
            ],
          },
        ],
      },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} />);

  assert.equal(html.includes("Rehab / Mobility"), true);
  assert.equal(html.includes("Neutral-Grip Isometric Holds"), true);
  assert.equal(html.includes("Full rest between holds"), false);
  assert.equal(html.includes("Easy Assault Bike"), false);
  assert.equal(html.includes("Show more (2 blocks)"), true);
});

test("renders fallback safety card from active notes when red flag rules are absent", () => {
  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    plan_notes: [
      {
        category: "injury",
        label: "Elbow cut",
        text: "Stop immediately and report if the wound reopens or sharp pain increases.",
      },
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

  assert.equal(html.includes("Safety priority"), true);
  assert.equal(html.includes("Red flags - stop"), true);
  assert.equal(html.includes("Safety note"), true);
  assert.equal(html.includes("Stop immediately and report"), true);
});

test("attaches deterministic nutrition and recovery to matching week phases", () => {
  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    weeks: [
      {
        week_id: "wk-1",
        week_index: 1,
        phase_label: "GPP",
        days: [],
      },
      {
        week_id: "wk-2",
        week_index: 2,
        phase_label: "SPP",
        days: [],
      },
    ],
    deterministic_support: {
      nutrition: {
        by_phase: {
          GPP: {
            protein_g_per_day: { min: 168, max: 210 },
            hydration_ml_per_day: { min: 3150, max: 4200 },
            meal_structure: "3 core meals",
          },
          SPP: {
            carbs_g_per_day: { min: 315, max: 630 },
          },
        },
      },
      recovery: {
        by_phase: {
          GPP: {
            sleep_hours_target: [8, 9],
            phase_focus: ["Reset sleep routine"],
          },
        },
      },
    },
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} />);
  const week1Index = html.indexOf("Week 1");
  const nutritionIndex = html.indexOf("Nutrition");
  const week2Index = html.indexOf("Week 2");

  assert.equal(week1Index >= 0, true);
  assert.equal(nutritionIndex > week1Index, true);
  assert.equal(nutritionIndex < week2Index, true);
  assert.equal(html.includes("Hide General prep nutrition"), true);
  assert.equal(html.includes("Hide General prep recovery"), true);
  assert.equal(html.includes("Hide Specific prep nutrition"), true);
  assert.equal(html.includes("General prep +"), false);
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
