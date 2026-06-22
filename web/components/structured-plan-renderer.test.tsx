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

// Builds a single-session day where the session-level and day-card mindsets can
// be varied independently, exercising the SessionCard mindset fallback.
function mindsetPlan({
  sessionMindset,
  dayCardMindset,
}: {
  sessionMindset?: unknown;
  dayCardMindset?: unknown;
}): StructuredPlan {
  return {
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
              ...(dayCardMindset !== undefined ? { mindset_anchor: dayCardMindset } : {}),
            },
            sessions: [
              {
                session_id: "ses-1",
                session_type: "sparring",
                title: "Hard sparring",
                ...(sessionMindset !== undefined ? { mindset_anchor: sessionMindset } : {}),
                blocks: [{ block_id: "blk-1", display_name: "Live rounds" }],
              },
            ],
          },
        ],
      },
    ],
  } as StructuredPlan;
}

test("session card falls back to the day card mindset when the session has none", () => {
  const html = renderToStaticMarkup(
    <StructuredPlanRenderer
      plan={mindsetPlan({
        dayCardMindset: { intent: "Day card mindset intent", focus_cue: "Day card focus cue" },
      })}
    />,
  );

  assert.equal(html.includes("Day card mindset intent"), true);
  assert.equal(html.includes("Day card focus cue"), true);
});

test("session card falls back when the session mindset has no displayable content", () => {
  const html = renderToStaticMarkup(
    <StructuredPlanRenderer
      plan={mindsetPlan({
        sessionMindset: {},
        dayCardMindset: { intent: "Day card mindset intent", focus_cue: "Day card focus cue" },
      })}
    />,
  );

  assert.equal(html.includes("Day card mindset intent"), true);
  assert.equal(html.includes("Day card focus cue"), true);
});

test("session card prefers its own mindset when it has displayable content", () => {
  const html = renderToStaticMarkup(
    <StructuredPlanRenderer
      plan={mindsetPlan({
        sessionMindset: { intent: "Session mindset intent", focus_cue: "Session focus cue" },
        dayCardMindset: { intent: "Day card mindset intent", focus_cue: "Day card focus cue" },
      })}
    />,
  );

  assert.equal(html.includes("Session mindset intent"), true);
  assert.equal(html.includes("Session focus cue"), true);
  assert.equal(html.includes("Day card mindset intent"), false);
  assert.equal(html.includes("Day card focus cue"), false);
});

test("session card renders no mindset block when both mindsets are blank", () => {
  const html = renderToStaticMarkup(
    <StructuredPlanRenderer plan={mindsetPlan({ sessionMindset: {}, dayCardMindset: {} })} />,
  );

  assert.equal(html.includes("Mindset"), false);
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

test("collapses deterministic nutrition and recovery into a support section at the bottom", () => {
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

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} today={new Date(2030, 0, 1)} />);

  // The week strip exposes both weeks as pills.
  assert.equal(html.includes("W1"), true);
  assert.equal(html.includes("W2"), true);
  // Support sits in its own collapsed section near the bottom (after the weeks).
  const supportIndex = html.indexOf("Support");
  assert.equal(supportIndex > html.indexOf("W2"), true);
  assert.equal(html.includes("Show recovery"), true);
  assert.equal(html.includes("Show nutrition"), true);
  // Deterministic per-phase content still renders inside the support section.
  assert.equal(html.includes("General prep"), true);
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

test("marks the current day and surfaces the camp status + week focus", () => {
  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    event_context: { fight_date: "2026-07-17" },
    red_flag_rules: [
      { rule_id: "rf-1", severity: "red", display_text: "Stop if Achilles pain is high." },
    ],
    weeks: [
      {
        week_id: "wk-1",
        week_index: 4,
        phase_label: "SPP",
        week_goal: "Convert strength into speed.",
        days: [
          {
            date: "2026-06-19",
            day_type: "high",
            countdown_label: "D-28",
            today_card: { headline: "Train as planned" },
            sessions: [
              { session_id: "s1", title: "Lower power", completion_status: "done", blocks: [] },
            ],
          },
        ],
      },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} today={new Date(2026, 5, 19)} />);

  // Camp status chips and countdown.
  assert.equal(html.includes("Week 1 of 1"), true);
  assert.equal(html.includes("D-28"), true);
  // Week focus still surfaces via the week overview (the separate readiness
  // cube strip was removed as bloat — the camp map header carries status now).
  assert.equal(html.includes("Convert strength into speed."), true);
  // The standalone "Today call" / "Injury watch" cubes are gone.
  assert.equal(html.includes("Today call"), false);
  assert.equal(html.includes("Injury watch"), false);
  // Current day is flagged.
  assert.equal(html.includes("cm-day-current"), true);
  assert.equal(html.includes("1/1 done"), true);
});

test("renders the raw markdown fallback collapsed at the bottom", () => {
  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    weeks: [{ week_id: "wk-1", week_index: 1, phase_label: "GPP", days: [] }],
    raw_markdown_fallback: "## Original plan\nLegacy text body.",
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} today={new Date(2030, 0, 1)} />);

  assert.equal(html.includes("Original plan text"), true);
  assert.equal(html.includes("Legacy text body."), true);
  assert.equal(html.includes("cm-raw-fallback"), true);
});

test("uses an athlete-readable camp-map command header, not internal wording", () => {
  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    weeks: [{ week_id: "wk-1", week_index: 1, phase_label: "GPP", days: [] }],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} />);

  assert.equal(html.includes("Camp map"), true);
  assert.equal(html.includes("Structured plan"), false);
});

test("does not leak raw enum tokens for day type or session type", () => {
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
            date: "2026-06-19",
            day_type: "high",
            countdown_label: "D-28",
            today_card: { readiness_status: "train_as_planned" },
            sessions: [
              {
                session_id: "s1",
                session_type: "strength_power",
                title: "Lower power",
                blocks: [],
              },
            ],
          },
        ],
      },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} today={new Date(2026, 5, 19)} />);

  assert.equal(html.includes("strength_power"), false);
  assert.equal(html.includes("Strength &amp; power"), true);
  // The readiness/"train as planned" tag was removed as bloat — the app owns
  // that decision (it surfaces on Today), so it must not appear in the map at all.
  assert.equal(html.includes("train_as_planned"), false);
  assert.equal(html.includes("Train as planned"), false);
});

test("a session-less rest day does not render an awkward '0 sessions' tag", () => {
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
            date: "2026-06-21",
            day_type: "rest",
            today_card: {},
            sessions: [],
          },
        ],
      },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} today={new Date(2026, 5, 21)} />);

  assert.equal(html.includes("0 session"), false);
});

test("week overview separates training days, app sessions, and coach-led sessions", () => {
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
            date: "2026-06-18",
            day_type: "high",
            sessions: [{ session_id: "s1", title: "Lower strength", blocks: [] }],
          },
          {
            date: "2026-06-19",
            day_type: "moderate",
            sessions: [{ session_id: "s2", title: "Conditioning", blocks: [] }],
          },
          {
            date: "2026-06-20",
            day_type: "high",
            today_card: { headline: "Coach-led boxing session" },
            sessions: [],
          },
          {
            date: "2026-06-21",
            day_type: "high",
            today_card: { headline: "Coach-led sparring" },
            sessions: [],
          },
          {
            date: "2026-06-22",
            day_type: "rest",
            sessions: [],
          },
        ],
      },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} today={new Date(2026, 5, 18)} />);

  assert.equal(html.includes("Training days"), true);
  assert.equal(html.includes("App sessions"), true);
  assert.equal(html.includes("Coach-led sessions"), true);
  assert.equal(html.includes("App completion"), true);
  assert.equal(html.includes("Days</span>"), false);
  assert.equal(html.includes("Completed</span>"), false);
});

test("completed work is tagged with the calm success tone, never the brand red accent", () => {
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
            date: "2026-06-19",
            day_type: "high",
            sessions: [
              { session_id: "s1", title: "Lower power", completion_status: "done", blocks: [] },
            ],
          },
        ],
      },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} today={new Date(2026, 5, 19)} />);

  assert.equal(html.includes("sp-done"), true);
  // The "done" completion tag must not borrow the red accent class.
  assert.equal(/class="sp-tag sp-accent"[^>]*>\s*1\/1 done/.test(html), false);
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
