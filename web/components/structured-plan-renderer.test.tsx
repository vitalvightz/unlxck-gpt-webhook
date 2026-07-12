import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { SessionCard, StructuredPlanRenderer } from "./structured-plan-renderer";
import type { StructuredPlan, StructuredSession } from "@/lib/types";

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

test("does not duplicate a rehab insert as a summary once the blocks are expanded", () => {
  // With the full blocks open, every rehab insert renders in full below, so the
  // compact Rehab / Mobility summary must not ALSO print — no two cards for one
  // insert.
  const session = {
    session_id: "ses-1",
    session_type: "conditioning",
    title: "Aerobic + rehab",
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
  } as unknown as StructuredSession;

  const html = renderToStaticMarkup(<SessionCard session={session} defaultOpenBlocks />);

  // Full rehab block (with its detail) shows exactly once; the summary eyebrow
  // is gone.
  assert.equal(html.includes("Neutral-Grip Isometric Holds"), true);
  assert.equal(html.includes("Full rest between holds"), true);
  assert.equal(html.includes("Rehab / Mobility"), false);
});

test("labels a stop rule stored in progression_rule as Stop rule, not Progress", () => {
  const session = {
    session_id: "ses-1",
    session_type: "strength_power",
    title: "Band-Resisted Straight Punch",
    blocks: [
      {
        block_id: "punch",
        block_type: "power",
        display_name: "Band-Resisted Straight Punch",
        sets: 2,
        reps: "6-8",
        progression_rule: "Stop the set if ankle pain increases or punch speed drops.",
      },
    ],
  } as unknown as StructuredSession;

  const html = renderToStaticMarkup(<SessionCard session={session} defaultOpenBlocks />);

  assert.equal(html.includes("Stop rule"), true);
  assert.equal(html.includes("Stop the set if ankle pain increases"), true);
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
  // Recovery and Nutrition sit in their own collapsed sections near the bottom
  // (after the weeks), each toggled independently.
  assert.equal(html.includes("Show recovery"), true);
  assert.equal(html.includes("Show nutrition"), true);
  assert.equal(html.indexOf("Show recovery") > html.indexOf("W2"), true);
  assert.equal(html.indexOf("Show nutrition") > html.indexOf("W2"), true);
  // Deterministic per-phase content still renders inside the support sections.
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

test("renders light technical context alongside app sessions in the same day card", () => {
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
            day_type: "moderate",
            today_card: { headline: "Light technical combat" },
            sessions: [
              { session_id: "s1", session_type: "strength", title: "Lower strength", blocks: [] },
            ],
          },
        ],
      },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} />);

  assert.equal(html.includes("Light technical combat"), true);
  assert.equal(html.includes("Lower strength"), true);
  assert.equal(html.includes("Low-noise app work can stay on this day if prescribed."), true);
  assert.equal(html.includes("sp-day-card-light_combat"), false);
  assert.ok(html.indexOf("Light technical combat") < html.indexOf("Lower strength"));
});

test("surfaces coach-led contact alongside app sessions in the same day card", () => {
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
            date: "2026-06-16",
            countdown_label: "D-12",
            day_type: "moderate",
            today_card: {
              headline: "Tactical Cue Card",
              coach_led_contact: "Coach-led boxing — technical only",
            },
            sessions: [
              { session_id: "s1", session_type: "skill", title: "Tactical Cue Card", blocks: [] },
            ],
          },
        ],
      },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} />);

  // Both the coach-owned contact and the app session render in the one day card,
  // with the contact surfaced above the app work.
  assert.equal(html.includes("Coach-led boxing — technical only"), true);
  assert.equal(html.includes("Tactical Cue Card"), true);
  assert.equal(html.includes("Coach-owned contact today"), true);
  assert.ok(
    html.indexOf("Coach-led boxing — technical only") < html.indexOf(">Tactical Cue Card<"),
  );
});

test("marks the current day and surfaces the camp status + week focus", () => {
  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    event_context: { fight_date: "2026-07-17" },
    red_flag_rules: [
      { rule_id: "rf-1", severity: "red", display_text: "Stop if Achilles pain is high." },
    ],
    plan_notes: [{ category: "injury", label: "Achilles", text: "Watch Achilles load." }],
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
            today_card: { headline: "Speed conversion", readiness_status: "train_as_planned" },
            sessions: [
              { session_id: "s1", title: "Lower power", completion_status: "done", blocks: [] },
            ],
          },
        ],
      },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} today={new Date(2026, 5, 19)} />);

  // Countdown + week focus surface via the week strip / overview.
  assert.equal(html.includes("D-28"), true);
  assert.equal(html.includes("Convert strength into speed."), true);
  // The day's readiness_status must never leak the exact train/modify/pull-back
  // call — that stays on Today.
  assert.equal(html.includes("Train as planned"), false);
  assert.equal(html.includes("train_as_planned"), false);
  // Current day is flagged, and its completion shows on the day card.
  assert.equal(html.includes("cm-day-current"), true);
  assert.equal(html.includes("1/1 done"), true);
});

test("compresses the plan: dedupes safety, folds the disclaimer, trims the week overview", () => {
  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    red_flag_rules: [
      {
        rule_id: "rf-1",
        severity: "red",
        display_text:
          "If weight-cut symptoms worsen (lightheadedness), stop non-essential activity and escalate to coach/medical staff.",
      },
    ],
    plan_notes: [
      // A paraphrase of the red flag (minus the parenthetical) — dropped from Active notes.
      {
        category: "weight_cut",
        label: "Weight cut",
        text: "If weight-cut symptoms worsen, stop non-essential activity and escalate to coach/medical staff.",
      },
      // Genuine context that only shares a phrase with the flag — kept.
      {
        category: "injury",
        label: "Left shoulder contusion",
        text: "Avoid direct contact; rehab drills included each session.",
      },
    ],
    weeks: [
      {
        week_id: "wk-1",
        week_index: 1,
        phase_label: "SPP",
        week_goal: "Build single-leg drive.",
        days: [
          {
            date: "2026-06-19",
            day_type: "moderate",
            sessions: [{ session_id: "s1", title: "Lower", blocks: [] }],
          },
        ],
      },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} today={new Date(2026, 5, 19)} />);
  const count = (needle: string) => html.split(needle).length - 1;

  // The medical disclaimer is folded into the Red Flags card — exactly one
  // safety-note block, no standalone banner duplicate.
  assert.equal(count('class="safety-note '), 1);
  // The Active note that just restated the red flag is dropped; the contextual
  // injury note stays, and the escalation sentence renders once (in Red Flags).
  assert.equal(html.includes("rehab drills included each session"), true);
  assert.equal(count("stop non-essential activity and escalate"), 1);
  // The week overview no longer prints a Phase stat row (phase lives in the
  // status chips and the week pill).
  assert.equal(html.includes(">Phase</span>"), false);
  // The week goal shows once — in the overview heading, not repeated as a body line.
  assert.equal(count("Build single-leg drive."), 1);
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

// NOTE: the earlier "command header" tests (a header rendering "Camp map",
// plan-status colouring, and a "Generated {date}" line from the createdAt /
// planStatus props) were removed with the camp-map redesign — those props are
// intentionally not rendered on this plan view (see the prop doc-comments in
// structured-plan-renderer.tsx). Their tests were deleted rather than kept
// asserting a removed subsystem.

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

test("does not render day intensity tags on session cards", () => {
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
            date: "2026-06-26",
            day_type: "high",
            countdown_label: "D-6",
            sessions: [
              {
                session_id: "s1",
                session_type: "mixed",
                title: "Fight-Speed Primer",
                blocks: [],
              },
            ],
          },
        ],
      },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} today={new Date(2026, 5, 26)} />);

  assert.equal(html.includes(">High</span>"), false);
  assert.equal(html.includes("Mixed session"), true);
});

test("always shows the weight-cut symptom red flag, de-emphasised below moderate risk", () => {
  const basePlan = {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    red_flag_rules: [
      {
        rule_id: "rf-weight",
        severity: "red",
        display_text:
          "If weight-cut symptoms worsen (lightheadedness), stop non-essential activity and escalate to coach/medical staff.",
      },
    ],
    plan_notes: [
      {
        category: "weight_cut",
        label: "Weight cut",
        text: "If weight-cut symptoms worsen, stop non-essential activity and escalate to coach/medical staff.",
      },
    ],
    weeks: [{ week_id: "wk-1", week_index: 1, phase_label: "TAPER", days: [] }],
  } satisfies StructuredPlan;

  const moderate = renderToStaticMarkup(
    <StructuredPlanRenderer
      plan={{
        ...basePlan,
        deterministic_support: {
          nutrition: { by_phase: { TAPER: { weight_cut: { active: true, risk_band: "moderate" } } } },
        },
      }}
    />,
  );
  // Below moderate risk: the explicit symptom red flag is STILL shown (a
  // symptom-based stop/escalate rule is never hidden by a predicted risk band),
  // just visually de-emphasised so it does not lead the card.
  assert.equal(moderate.includes("weight-cut symptoms worsen"), true);
  assert.equal(moderate.includes("sp-redflag-deemphasised"), true);
  // The redundant duplicate copy in the general Active Notes card stays deduped,
  // so the escalation sentence renders exactly once (in Red Flags).
  assert.equal(countOccurrences(moderate, "stop non-essential activity"), 1);

  const high = renderToStaticMarkup(
    <StructuredPlanRenderer
      plan={{
        ...basePlan,
        deterministic_support: {
          nutrition: { by_phase: { TAPER: { weight_cut: { active: true, risk_band: "high" } } } },
        },
      }}
    />,
  );
  // At/above moderate: shown at full weight (never de-emphasised).
  assert.equal(high.includes("weight-cut symptoms worsen"), true);
  assert.equal(high.includes("sp-redflag-deemphasised"), false);
  assert.equal(countOccurrences(high, "stop non-essential activity"), 1);
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
  // The week-overview stats no longer say "app" — the athlete just sees their work.
  assert.equal(html.includes("Sessions</span>"), true);
  assert.equal(html.includes("Coach-led</span>"), true);
  assert.equal(html.includes("Completion</span>"), true);
  assert.equal(html.includes("App sessions"), false);
  assert.equal(html.includes("App completion"), false);
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
