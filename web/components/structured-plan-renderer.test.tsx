import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import {
  buildDayTimeline,
  SessionCard,
  StructuredPlanRenderer,
  weekStripCenterOffset,
} from "./structured-plan-renderer";
import { openBlockWeekIntent } from "@/lib/open-block";
import { formatPlanLabel } from "@/lib/plan-labels";
import type {
  PlanScheduleContext,
  RehabLabelPolicy,
  StructuredPlan,
  StructuredSession,
} from "@/lib/types";

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
                  reset_cue: "Breathe and reset",
                  confidence_anchor: "Rounds are banked",
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
  // A non-current day keeps a neutral countdown (red is reserved for today).
  assert.equal(html.includes('<span class="sp-countdown cm-day-countdown">D-19</span>'), true);
  assert.equal(html.includes("sp-countdown cm-day-countdown sp-accent"), false);
  assert.equal(html.includes('<span class="sp-week-title cm-day-title">Mon</span>'), true);
  // The closed row shows only the completion fraction — no session-count pill.
  assert.equal(html.includes("1 session"), false);
  assert.equal(html.includes("Morning intro duplicate"), false); // headline not shown on session days
  // The more specific session mindset suppresses the broader day fallback.
  assert.equal(html.includes("Duplicate intro intent"), false);
  assert.equal(html.includes("Breathing reset"), false);
  assert.equal(html.includes("MORE"), false);
  assert.equal(html.includes("LESS"), false);
  assert.equal(html.includes("Show more (1 block)"), true);
  assert.equal(html.includes("Context"), true);
  assert.equal(html.includes("Taper freshness day"), true);
  // The full mindset anchor renders on the session card, including the reset
  // cue and confidence anchor (the mental content, not just training focus).
  assert.equal(html.includes("Breathe and reset"), true);
  assert.equal(html.includes("Rounds are banked"), true);
});

test("open-plan weekday fallback labels today with the live date, not the projected date", () => {
  const plan = {
    schema_version: "text-adapter.v1",
    plan_metadata: { title: "Open plan", plan_type: "open_ongoing_system" },
    weeks: [
      { week_id: "week-1", week_index: 1, days: [] },
      {
        week_id: "week-2",
        week_index: 2,
        days: [
          {
            date: "2026-08-15",
            weekday: "Sat",
            sessions: [{ session_id: "sat-strength", title: "Saturday strength", blocks: [] }],
          },
        ],
      },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(
    <StructuredPlanRenderer
      plan={plan}
      today={new Date(2026, 6, 18)}
      openOngoing
      scheduleContext={{
        schedule_mode: "open_recurring",
        projection_status: "projected",
        current_week_number: 2,
      }}
    />,
  );

  assert.equal(html.includes("SAT 18 JUL"), true);
  assert.equal(html.includes("SAT 15 AUG"), false);
});

test("structured renderer normalizes legacy D0 event-day labels to D-0", () => {
  const plan = {
    schema_version: "1.0",
    event_context: { fight_date: "2026-07-17" },
    weeks: [
      {
        week_id: "fight-week",
        week_index: 1,
        countdown_start: "D0",
        countdown_end: "D0",
        days: [
          {
            date: "2026-07-17",
            countdown_label: "D0",
            day_type: "rest",
            sessions: [],
          },
        ],
      },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} />);

  assert.equal(html.includes(">D0<"), false);
  assert.equal(html.includes("D-0"), true);
});

test("open ongoing renderer uses renewable block labels instead of fight-camp phases", () => {
  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Open Plan", sport: "boxing", plan_type: "fight_camp" },
    deterministic_support: {
      nutrition: {
        by_phase: {
          GPP: { protein_g_per_day: { min: 140, max: 160 } },
          SPP: { protein_g_per_day: { min: 150, max: 170 } },
          TAPER: { protein_g_per_day: { min: 145, max: 165 } },
        },
      },
      recovery: {
        by_phase: {
          GPP: { sleep_hours_target: [8, 9] },
          SPP: { sleep_hours_target: [8, 9] },
          TAPER: { sleep_hours_target: [8, 9] },
        },
      },
    },
    weeks: [
      { week_id: "wk-1", week_index: 1, phase_label: "SPP", week_goal: "Baseline", days: [{ date: "", day_type: "high", sessions: [] }] },
      { week_id: "wk-2", week_index: 2, phase_label: "SPP", week_goal: "Small progression", days: [] },
      { week_id: "wk-3", week_index: 3, phase_label: "SPP", week_goal: "Highest controlled week", days: [] },
      { week_id: "wk-4", week_index: 4, phase_label: "SPP", week_goal: "Deload and reassess", days: [] },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} openOngoing />);

  assert.equal(html.includes('aria-label="Training block weeks"'), true);
  for (const label of ["Baseline", "Progress", "Highest Controlled", "Deload + Reassess"]) {
    assert.equal(html.includes(`cm-week-pill-phase" title="${label}">${label}</span>`), true);
  }
  assert.equal(html.includes("Specific prep"), false);
  assert.equal(html.includes("General prep"), false);
  assert.equal(html.includes(">Taper<"), false);
  assert.equal(html.includes(">Load</span>"), false);
  assert.equal(html.includes("Block 1 · Week 1 of 4"), true);
  assert.equal(countOccurrences(html, "Current block"), 6);
});

test("open ongoing renderer falls back when schedule and week numbers are non-finite", () => {
  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Open Plan", sport: "boxing", plan_type: "fight_camp" },
    weeks: [
      {
        week_id: "wk-bad",
        week_index: Number.NaN,
        phase_label: "SPP",
        week_goal: "Baseline",
        days: [],
      },
    ],
  } as unknown as StructuredPlan;
  const scheduleContext: PlanScheduleContext = {
    schedule_mode: "open_recurring",
    projection_status: "projected",
    current_week_number: Number.NaN,
  };

  const html = renderToStaticMarkup(
    <StructuredPlanRenderer
      plan={plan}
      openOngoing
      scheduleContext={scheduleContext}
    />,
  );

  assert.equal(html.includes("Week 1 of 4"), true);
  assert.equal(html.includes("NaN"), false);
});

// Builds a day whose day-card mindset and per-session mindsets can be varied
// independently. Each entry in `sessionMindsets` becomes one session; `undefined`
// omits the session's mindset_anchor, an object supplies one. This exercises the
// rule that SESSION mindsets take priority and the DAY mindset is only a
// fallback when no session defines a usable anchor.
function mindsetPlan({
  dayCardMindset,
  sessionMindsets,
}: {
  dayCardMindset?: unknown;
  sessionMindsets: unknown[];
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
            sessions: sessionMindsets.map((sessionMindset, index) => ({
              session_id: `ses-${index + 1}`,
              session_type: "sparring",
              title: `Session ${index + 1}`,
              ...(sessionMindset !== undefined ? { mindset_anchor: sessionMindset } : {}),
              blocks: [{ block_id: `blk-${index + 1}`, display_name: "Live rounds" }],
            })),
          },
        ],
      },
    ],
  } as StructuredPlan;
}

// Each rendered MindsetAnchorCard emits exactly one `sp-mindset-list`, so its
// count is the number of distinct mindset cards on screen.
function mindsetCardCount(html: string): number {
  return countOccurrences(html, "sp-mindset-list");
}

test("mindset scenario 1: day mindset is the fallback when sessions have none", () => {
  const html = renderToStaticMarkup(
    <StructuredPlanRenderer
      plan={mindsetPlan({
        dayCardMindset: { intent: "Day-only intent", focus_cue: "Day-only focus" },
        sessionMindsets: [undefined],
      })}
    />,
  );

  assert.equal(mindsetCardCount(html), 1);
  assert.equal(countOccurrences(html, "Day-only intent"), 1);
  assert.equal(html.includes("Day-only focus"), true);
});

test("mindset scenario 2: session mindset only renders on its session card", () => {
  const html = renderToStaticMarkup(
    <StructuredPlanRenderer
      plan={mindsetPlan({
        sessionMindsets: [{ intent: "Session-only intent", focus_cue: "Session-only focus" }],
      })}
    />,
  );

  assert.equal(mindsetCardCount(html), 1);
  assert.equal(html.includes("Session-only intent"), true);
  assert.equal(html.includes("Session-only focus"), true);
});

test("mindset scenario 3: session mindsets suppress the day fallback", () => {
  const html = renderToStaticMarkup(
    <StructuredPlanRenderer
      plan={mindsetPlan({
        dayCardMindset: { intent: "Day intent", focus_cue: "Day focus" },
        sessionMindsets: [
          { intent: "Session A intent", focus_cue: "Session A focus" },
          { intent: "Session B intent", focus_cue: "Session B focus" },
        ],
      })}
    />,
  );

  assert.equal(mindsetCardCount(html), 2);
  assert.equal(html.includes("Day intent"), false);
  assert.equal(html.includes("Session A intent"), true);
  assert.equal(html.includes("Session B intent"), true);
});

test("mindset scenario 4: any session mindset suppresses the day fallback", () => {
  const html = renderToStaticMarkup(
    <StructuredPlanRenderer
      plan={mindsetPlan({
        dayCardMindset: { intent: "Day intent", focus_cue: "Day focus" },
        sessionMindsets: [
          { intent: "Owning session intent", focus_cue: "Owning session focus" },
          undefined,
        ],
      })}
    />,
  );

  // Keep the specific anchor; the session without one does not repeat the day.
  assert.equal(mindsetCardCount(html), 1);
  assert.equal(html.includes("Day intent"), false);
  assert.equal(html.includes("Owning session intent"), true);
});

test("mindset scenario 5: no mindset anywhere renders no mindset block", () => {
  const html = renderToStaticMarkup(
    <StructuredPlanRenderer
      plan={mindsetPlan({ dayCardMindset: {}, sessionMindsets: [{}, undefined] })}
    />,
  );

  assert.equal(mindsetCardCount(html), 0);
  assert.equal(html.includes(">Mindset<"), false);
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

// A one-session plan whose only rehab block targets the hamstring. The tag on
// that block is the thing under test in the label cases below.
function hamstringRehabPlan(): StructuredPlan {
  return {
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
                    display_name: "Isometric Hamstring Bridge Hold",
                    sets: 2,
                    reps: "12-15 s",
                  },
                ],
              },
            ],
          },
        ],
      },
    ],
  } satisfies StructuredPlan;
}

const HAMSTRING_OPEN: RehabLabelPolicy = {
  default_mode: "prehab",
  active_regions: [{ region: "hamstring", terms: ["hamstring", "hamstrings"] }],
};

const QUAD_OPEN_HAMSTRING_CLEARED: RehabLabelPolicy = {
  default_mode: "prehab",
  active_regions: [{ region: "quads", terms: ["quad", "quads", "quadriceps"] }],
};

test("without a policy every rehab block keeps the Rehab wording", () => {
  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={hamstringRehabPlan()} />);
  assert.equal(html.includes("Rehab / Mobility"), true);
  assert.equal(html.includes("Prehab / Mobility"), false);
});

test("a rehab block whose region is still injured stays Rehab", () => {
  const html = renderToStaticMarkup(
    <StructuredPlanRenderer plan={hamstringRehabPlan()} rehabLabelPolicy={HAMSTRING_OPEN} />,
  );
  assert.equal(html.includes("Rehab / Mobility"), true);
  assert.equal(html.includes("Prehab / Mobility"), false);
});

test("a cleared region reads Prehab even while another region is injured", () => {
  // The regression: one open quad flag used to pin the whole plan to "Rehab",
  // so cleared hamstring work kept reading Rehab.
  const html = renderToStaticMarkup(
    <StructuredPlanRenderer
      plan={hamstringRehabPlan()}
      rehabLabelPolicy={QUAD_OPEN_HAMSTRING_CLEARED}
    />,
  );
  assert.equal(html.includes("Prehab / Mobility"), true);
  assert.equal(html.includes("Rehab / Mobility"), false);
});

test("an unlocalizable open injury keeps every rehab block on Rehab", () => {
  const html = renderToStaticMarkup(
    <StructuredPlanRenderer
      plan={hamstringRehabPlan()}
      rehabLabelPolicy={{ default_mode: "rehab", active_regions: [] }}
    />,
  );
  assert.equal(html.includes("Rehab / Mobility"), true);
  assert.equal(html.includes("Prehab / Mobility"), false);
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

test("labels the session objective as the Why and sentence-cases it", () => {
  // Objectives arrive from the plan conversion in mixed casing (usually all
  // lower-case), which read as a typo under the Title Case session name — and
  // unlabelled they read as a description of the work rather than its reason.
  const session = {
    session_id: "ses-1",
    session_type: "mixed",
    title: "Neural Visualization",
    objective: "refine motor plan and composure without physical load",
    blocks: [{ block_id: "b1", display_name: "Quiet rehearsal" }],
  } as unknown as StructuredSession;

  const html = renderToStaticMarkup(<SessionCard session={session} />);

  assert.equal(html.includes("Refine motor plan and composure without physical load"), true);
  assert.equal(html.includes("refine motor plan and composure"), false);
  assert.equal(html.includes(">Why<"), true);
});

test("drops a mindset Context line that only restates the session objective", () => {
  // The objective already prints under the title; a Context anchor that repeats
  // it (bar casing/trailing period) must not print the same sentence twice, but
  // the other mindset lines and a genuinely distinct Context must stay.
  const session = {
    session_id: "ses-1",
    session_type: "skill",
    title: "Technical Shadow Rhythm",
    objective: "Timing and coordination rehearsal without physiological cost",
    mindset_anchor: {
      intent: "Reinforce entries/exits and rhythm",
      focus_cue: "Continuous smooth rounds",
      context: "Timing and coordination rehearsal without physiological cost.",
    },
    blocks: [{ block_id: "b1", display_name: "Shadow rounds" }],
  } as unknown as StructuredSession;

  const html = renderToStaticMarkup(<SessionCard session={session} defaultOpenBlocks />);

  // The objective sentence appears once (the title subtitle), not twice.
  assert.equal(
    countOccurrences(html, "Timing and coordination rehearsal without physiological cost"),
    1,
  );
  // The duplicate Context row is gone, but Intent/Focus remain.
  assert.equal(html.includes("Context"), false);
  assert.equal(html.includes("Reinforce entries/exits and rhythm"), true);
  assert.equal(html.includes("Continuous smooth rounds"), true);
});

test("keeps a mindset Context line that adds information beyond the objective", () => {
  const session = {
    session_id: "ses-2",
    session_type: "skill",
    title: "Sharp technical work",
    objective: "Sharpen decision rules for opening exchanges",
    mindset_anchor: {
      intent: "Sharpen decisions",
      context: "Pairs with coach-led technical session",
    },
    blocks: [{ block_id: "b1", display_name: "Drill" }],
  } as unknown as StructuredSession;

  const html = renderToStaticMarkup(<SessionCard session={session} defaultOpenBlocks />);

  assert.equal(html.includes("Context"), true);
  assert.equal(html.includes("Pairs with coach-led technical session"), true);
});

test("a malformed numeric payload never renders NaN / Infinity in the card", () => {
  // Every numeric field is deliberately malformed. The block detail is expanded
  // so the block renders in full, and the plan carries malformed macros, sleep
  // hours and week_index too — none of which may reach the DOM as text.
  const session = {
    session_id: "ses-1",
    session_type: "strength_power",
    title: "Malformed metrics",
    blocks: [
      {
        block_id: "b1",
        display_name: "Bad numbers",
        sets: Number.NaN,
        reps: Number.POSITIVE_INFINITY,
        rounds: -3,
        effort: { method: "RPE", value: Number.NaN },
        duration: { value: Number.NaN, unit: "seconds" },
        distance: { value: Number.POSITIVE_INFINITY, unit: "m" },
      },
      {
        // Malformed numeric STRING tokens must be stripped too, not just numbers.
        block_id: "b2",
        display_name: "Bad string numbers",
        sets: 3,
        reps: "Infinity",
        effort: { method: "RPE", value: "NaN" },
        load: { display: "-Infinity" },
      },
    ],
  } as unknown as StructuredSession;
  const sessionHtml = renderToStaticMarkup(<SessionCard session={session} defaultOpenBlocks />);
  assert.equal(sessionHtml.includes("NaN"), false);
  assert.equal(sessionHtml.includes("Infinity"), false);

  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    deterministic_support: {
      nutrition: {
        by_phase: {
          GPP: {
            protein_g_per_day: { min: Number.NaN, max: Number.POSITIVE_INFINITY },
            carbs_g_per_day: { min: -100, max: -50 },
          },
        },
      },
      recovery: { by_phase: { GPP: { sleep_hours_target: [Number.NaN, -2] } } },
    },
    weeks: [
      {
        week_id: "wk-1",
        week_index: Number.NaN,
        phase_label: "GPP",
        days: [{ date: "2026-06-17", day_type: "low", sessions: [session] }],
      },
    ],
  } as unknown as StructuredPlan;
  const planHtml = renderToStaticMarkup(
    <StructuredPlanRenderer plan={plan} today={new Date(2026, 5, 17)} />,
  );
  assert.equal(planHtml.includes("NaN"), false);
  assert.equal(planHtml.includes("Infinity"), false);
  // The week strip falls back to a positional label rather than "WNaN".
  assert.equal(planHtml.includes("WNaN"), false);
  assert.equal(planHtml.includes("W1"), true);
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

test("cleans malformed Regression and Stop coaching cues at render time", () => {
  const session = {
    session_id: "ses-legacy",
    session_type: "mobility",
    title: "Mobility reset",
    blocks: [
      {
        block_id: "mobility",
        block_type: "mobility",
        display_name: "Mobility Reset Flow",
        coaching_cues: [
          "Regression /",
          "Stay smooth through the range.",
          "Stop: switch to breathing only if shoulder pain rises.",
        ],
        regression_options: ["Use a smaller range."],
      },
    ],
  } as unknown as StructuredSession;

  const html = renderToStaticMarkup(<SessionCard session={session} defaultOpenBlocks />);

  assert.equal(html.includes("Regression /"), false);
  assert.equal(html.includes("Stay smooth through the range."), true);
  assert.equal(html.includes(">Easier</span>"), true);
  assert.equal(html.includes(">Stop rule</span>"), true);
  assert.equal(countOccurrences(html, "switch to breathing only if shoulder pain rises."), 1);
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
  assert.equal(countOccurrences(html, "Stop immediately and report"), 1);
});

test("keeps calm lead notes out of Red Flags while retaining the safety disclaimer", () => {
  const leadText =
    "Target weight is not set; coach owns the final call and programmed support stays active.";
  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    plan_notes: [
      {
        category: "weight_cut",
        label: "Lead notes",
        text: leadText,
      },
    ],
    weeks: [{ week_id: "wk-1", week_index: 1, phase_label: "TAPER", days: [] }],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} />);

  assert.equal(countOccurrences(html, leadText), 1);
  assert.equal(html.includes("Active notes"), true);
  assert.equal(html.includes("Red flags - stop"), true);
  assert.equal(countOccurrences(html, 'class="safety-note '), 1);
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
  // The genuine rest day renders as a single compact, non-expandable rest row.
  assert.equal(countOccurrences(html, "cm-rest-day"), 1);
  assert.equal(html.includes("Rest day."), false);
});

test("open plans keep session categories inside chronological day cards", () => {
  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Open Plan", sport: "boxing", plan_type: "fight_camp" },
    weeks: [
      {
        week_id: "wk-1",
        week_index: 1,
        phase_label: "GPP",
        days: [
          {
            date: "2026-07-13",
            weekday: "Mon",
            day_type: "moderate",
            today_card: { headline: "Support Strength" },
            sessions: [{ session_id: "s1", title: "Support Strength", blocks: [] }],
          },
          {
            date: "2026-07-15",
            weekday: "Wed",
            day_type: "high",
            today_card: { headline: "Coach-led boxing" },
            sessions: [],
          },
        ],
      },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(
    <StructuredPlanRenderer
      plan={plan}
      openOngoing
      today={new Date(2026, 6, 13)}
      scheduleContext={{
        schedule_mode: "open_recurring",
        projection_status: "projected",
        anchor_date: "2026-07-13",
        current_training_day: "2026-07-13",
        block_number: 1,
        current_week_number: 1,
      }}
    />,
  );

  assert.equal(html.includes('<span class="sp-week-title cm-day-title">MON 13 JUL</span>'), true);
  assert.equal(html.includes('<span class="sp-week-title cm-day-title">WED 15 JUL</span>'), true);
  assert.equal(html.includes('<span class="sp-week-title cm-day-title">Support Strength</span>'), false);
  assert.equal(html.includes("Support Strength"), true);
  assert.equal(html.includes("D-"), false);
  assert.equal(html.includes("Block 1"), true);
});

test("ambiguous open plans fail closed instead of using category names as dates", () => {
  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Open Plan", sport: "boxing", plan_type: "fight_camp" },
    raw_markdown_fallback: "## Weekly Rhythm\nMonday: Support Strength",
    weeks: [
      {
        week_id: "wk-1",
        week_index: 1,
        days: [
          {
            date: "",
            day_type: "moderate",
            today_card: { headline: "Support Strength" },
            sessions: [{ session_id: "s1", title: "Support Strength", blocks: [] }],
          },
        ],
      },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(
    <StructuredPlanRenderer
      plan={plan}
      openOngoing
      scheduleContext={{
        schedule_mode: "open_recurring",
        projection_status: "unavailable",
      }}
    />,
  );

  assert.equal(html.includes("Schedule unavailable"), true);
  assert.equal(html.includes('<span class="sp-week-title cm-day-title">Training day 1</span>'), true);
  assert.equal(html.includes('<span class="sp-week-title cm-day-title">Support Strength</span>'), false);
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
  // Current day is flagged, and its completion shows on the day card as the
  // compact success-toned fraction.
  assert.equal(html.includes("cm-day-current"), true);
  assert.equal(html.includes("cm-day-count-done"), true);
  assert.equal(html.includes("1/1"), true);
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

  // Constraints and stop actions must be seen before the training prescription.
  assert.ok(html.indexOf("Active notes") < html.indexOf(">Lower<"));
  assert.ok(html.indexOf("Red flags - stop") < html.indexOf(">Lower<"));

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

test("shows the raw markdown fallback to admins but hides it from athletes", () => {
  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    weeks: [{ week_id: "wk-1", week_index: 1, phase_label: "GPP", days: [] }],
    raw_markdown_fallback: "## Original plan\nLegacy text body.",
  } satisfies StructuredPlan;

  const adminHtml = renderToStaticMarkup(
    <StructuredPlanRenderer plan={plan} today={new Date(2030, 0, 1)} isAdmin />,
  );
  assert.equal(adminHtml.includes("Original plan text"), true);
  assert.equal(adminHtml.includes("Legacy text body."), true);
  assert.equal(adminHtml.includes("cm-raw-fallback"), true);

  // Default (athlete) view: the internal raw dump is gone entirely.
  const athleteHtml = renderToStaticMarkup(
    <StructuredPlanRenderer plan={plan} today={new Date(2030, 0, 1)} />,
  );
  assert.equal(athleteHtml.includes("Original plan text"), false);
  assert.equal(athleteHtml.includes("Legacy text body."), false);
  assert.equal(athleteHtml.includes("cm-raw-fallback"), false);
});

test("keeps the raw fallback for athletes in the fail-closed schedule-unavailable state", () => {
  // The on-screen message tells the athlete to read the original plan below, so
  // the raw text must remain reachable there even without admin.
  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Open Plan", sport: "boxing", plan_type: "fight_camp" },
    weeks: [{ week_id: "wk-1", week_index: 1, phase_label: "SPP", days: [] }],
    raw_markdown_fallback: "## Original plan\nLegacy text body.",
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(
    <StructuredPlanRenderer
      plan={plan}
      openOngoing
      scheduleContext={{ schedule_mode: "open_recurring", projection_status: "unavailable" }}
    />,
  );

  assert.equal(html.includes("Original plan text"), true);
  assert.equal(html.includes("Legacy text body."), true);
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

// Base plan carrying the weight-cut symptom escalation rule/note. `severity` is
// parameterised so we can prove a prominent severity overrides de-emphasis.
function weightCutPlan(severity: string): StructuredPlan {
  return {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    red_flag_rules: [
      {
        rule_id: "rf-weight",
        severity,
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
}

function withRiskBand(plan: StructuredPlan, riskBand: string): StructuredPlan {
  return {
    ...plan,
    deterministic_support: {
      nutrition: { by_phase: { TAPER: { weight_cut: { active: true, risk_band: riskBand } } } },
    },
  } as StructuredPlan;
}

test("weight-cut symptom red flag is de-emphasised ONLY when risk is explicitly below moderate", () => {
  // Low risk + non-prominent severity: shown but softened so it does not lead.
  const low = renderToStaticMarkup(
    <StructuredPlanRenderer plan={withRiskBand(weightCutPlan("amber"), "low")} />,
  );
  assert.equal(low.includes("weight-cut symptoms worsen"), true);
  assert.equal(low.includes("sp-redflag-deemphasised"), true);
  // The redundant duplicate copy in the general Active Notes card stays deduped,
  // so the escalation sentence renders exactly once (in Red Flags).
  assert.equal(countOccurrences(low, "stop non-essential activity"), 1);
});

test("weight-cut symptom red flag is NOT de-emphasised at moderate risk", () => {
  // Moderate is not BELOW moderate — it must render at full weight.
  const moderate = renderToStaticMarkup(
    <StructuredPlanRenderer plan={withRiskBand(weightCutPlan("amber"), "moderate")} />,
  );
  assert.equal(moderate.includes("weight-cut symptoms worsen"), true);
  assert.equal(moderate.includes("sp-redflag-deemphasised"), false);
});

test("weight-cut symptom red flag is NOT de-emphasised when risk data is missing", () => {
  // No deterministic_support at all: risk is unknown, never treated as low.
  const missing = renderToStaticMarkup(
    <StructuredPlanRenderer plan={weightCutPlan("amber")} />,
  );
  assert.equal(missing.includes("weight-cut symptoms worsen"), true);
  assert.equal(missing.includes("sp-redflag-deemphasised"), false);
});

test("an explicit red/critical severity rule is never de-emphasised, even below moderate risk", () => {
  // Even at low risk, an explicit high-severity rule overrides de-emphasis.
  for (const severity of ["red", "critical", "high"]) {
    const html = renderToStaticMarkup(
      <StructuredPlanRenderer plan={withRiskBand(weightCutPlan(severity), "low")} />,
    );
    assert.equal(html.includes("weight-cut symptoms worsen"), true);
    assert.equal(
      html.includes("sp-redflag-deemphasised"),
      false,
      `severity "${severity}" must never be faded`,
    );
  }
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

  assert.equal(html.includes("cm-day-count-done"), true);
  // The "done" completion fraction must not borrow the red accent class.
  assert.equal(/class="[^"]*sp-accent[^"]*"[^>]*>[^<]*1\/1/.test(html), false);
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

// --- open-plan development-block wave ---------------------------------------
//
// An open plan's four weeks share one weekly rhythm, so the block cards carry a
// week-directed instruction (progress / deload) instead of rendering as four
// identical clones. Dated camps never receive the intent and stay unchanged.

const waveSession = {
  session_id: "ses-wave",
  session_type: "strength_power",
  title: "Support Strength",
  blocks: [
    {
      block_id: "blk-progress",
      display_name: "Trap-bar deadlift",
      progression_rule: "Add 2.5 kg when all sets feel crisp.",
    },
    {
      block_id: "blk-stop",
      display_name: "Explosive med-ball throw",
      progression_rule: "Stop when throw speed drops.",
    },
  ],
} satisfies StructuredSession;

test("progression week: block cards surface their own rule once, stop rules stay", () => {
  const html = renderToStaticMarkup(
    <SessionCard
      session={waveSession}
      defaultOpenBlocks
      openWeekIntent={openBlockWeekIntent(2)}
    />,
  );

  // The rule renders as the week directive, not duplicated in the Progress aside.
  assert.equal(countOccurrences(html, "This week"), 2);
  assert.equal(countOccurrences(html, "Add 2.5 kg when all sets feel crisp."), 1);
  assert.equal(html.includes(">Progress</span>"), false);
  // The stop-rule block keeps its safety aside and gets the generic bump.
  assert.equal(countOccurrences(html, "Stop when throw speed drops."), 1);
  assert.equal(html.includes(">Stop rule</span>"), true);
  assert.equal(html.includes("only if last week felt controlled"), true);
});

test("deload week: block cards read as a volume cut, never a progression", () => {
  const html = renderToStaticMarkup(
    <SessionCard
      session={waveSession}
      defaultOpenBlocks
      openWeekIntent={openBlockWeekIntent(4)}
    />,
  );

  assert.equal(countOccurrences(html, "cut working sets roughly in half"), 2);
  assert.equal(html.includes("Add 2.5 kg when all sets feel crisp."), false);
  assert.equal(html.includes(">Stop rule</span>"), true);
});

test("without an open week intent the block asides render as before", () => {
  const html = renderToStaticMarkup(
    <SessionCard session={waveSession} defaultOpenBlocks />,
  );

  assert.equal(html.includes("This week"), false);
  assert.equal(html.includes(">Progress</span>"), true);
  assert.equal(countOccurrences(html, "Add 2.5 kg when all sets feel crisp."), 1);
});

test("open plan week overview headlines the block-week intent", () => {
  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Open Plan", sport: "boxing", plan_type: "open_ongoing_system" },
    weeks: [
      { week_id: "wk-1", week_index: 1, days: [{ weekday: "Mon", day_type: "moderate", sessions: [] }] },
      { week_id: "wk-2", week_index: 2, days: [] },
      { week_id: "wk-3", week_index: 3, days: [] },
      { week_id: "wk-4", week_index: 4, days: [] },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} openOngoing />);

  // Week 1 is selected by default → baseline intent line in the overview.
  assert.equal(html.includes("Run every dose as written and groove technical consistency."), true);

  const datedHtml = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} />);
  assert.equal(datedHtml.includes("Run every dose as written"), false);
});

// ---------------------------------------------------------------------------
// Countdown gap fill: missing dates between plan days render as rest rows so
// the D-countdown reads continuous instead of skipping numbers.

function gapFillPlan(
  days: Array<Record<string, unknown>>,
): StructuredPlan {
  return {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    weeks: [{ week_id: "wk-1", week_index: 1, phase_label: "SPP", days }],
  } as unknown as StructuredPlan;
}

test("buildDayTimeline fills intra-week date holes with countdown rest rows", () => {
  const days = [
    { date: "2026-07-07", countdown_label: "D-10", day_type: "high", sessions: [{ session_id: "s1", blocks: [] }] },
    { date: "2026-07-10", countdown_label: "D-7", day_type: "high", sessions: [{ session_id: "s2", blocks: [] }] },
  ] as unknown as Parameters<typeof buildDayTimeline>[0];

  const timeline = buildDayTimeline(days, true);

  assert.deepEqual(
    timeline.map((entry) => (entry.kind === "gap" ? `${entry.countdown}:${entry.weekday}` : entry.kind)),
    ["day", "D-9:Wed", "D-8:Thu", "day"],
  );
});

test("buildDayTimeline never synthesizes a countdown that contradicts the neighbours", () => {
  // Labels claim a 4-step drop but the dates are only 2 apart → weekday-only rows.
  const days = [
    { date: "2026-07-07", countdown_label: "D-10", day_type: "high", sessions: [] },
    { date: "2026-07-09", countdown_label: "D-6", day_type: "high", sessions: [] },
  ] as unknown as Parameters<typeof buildDayTimeline>[0];

  const timeline = buildDayTimeline(days, true);
  const gaps = timeline.filter((entry) => entry.kind === "gap");

  assert.equal(gaps.length, 1);
  assert.equal(gaps[0].kind === "gap" && gaps[0].countdown, null);
});

test("buildDayTimeline fails closed on missing dates, huge gaps, and disabled mode", () => {
  const noDates = [
    { weekday: "Mon", day_type: "high", sessions: [] },
    { weekday: "Fri", day_type: "high", sessions: [] },
  ] as unknown as Parameters<typeof buildDayTimeline>[0];
  assert.equal(buildDayTimeline(noDates, true).every((entry) => entry.kind === "day"), true);

  const hugeGap = [
    { date: "2026-07-01", countdown_label: "D-20", day_type: "high", sessions: [] },
    { date: "2026-07-11", countdown_label: "D-10", day_type: "high", sessions: [] },
  ] as unknown as Parameters<typeof buildDayTimeline>[0];
  assert.equal(buildDayTimeline(hugeGap, true).every((entry) => entry.kind === "day"), true);

  const dated = [
    { date: "2026-07-07", countdown_label: "D-10", day_type: "high", sessions: [] },
    { date: "2026-07-10", countdown_label: "D-7", day_type: "high", sessions: [] },
  ] as unknown as Parameters<typeof buildDayTimeline>[0];
  assert.equal(buildDayTimeline(dated, false).every((entry) => entry.kind === "day"), true);
});

test("renderer shows synthesized rest rows as inert rows, not accordions", () => {
  const plan = gapFillPlan([
    {
      date: "2026-07-07",
      countdown_label: "D-10",
      day_type: "high",
      sessions: [{ session_id: "s1", title: "Power", blocks: [] }],
    },
    {
      date: "2026-07-10",
      countdown_label: "D-7",
      day_type: "high",
      sessions: [{ session_id: "s2", title: "Conditioning", blocks: [] }],
    },
  ]);

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} today={new Date(2026, 6, 7)} />);

  assert.equal(countOccurrences(html, "cm-rest-day"), 2);
  assert.equal(html.includes("D-9"), true);
  assert.equal(html.includes("D-8"), true);
  // Rest rows are plain divs — the only <details> day rows are the two real days.
  assert.equal(countOccurrences(html, "cm-day-summary"), 2);
  // A synthesized gap has no backend signal, so it must NOT assert "Rest" — it
  // reads the honest neutral label instead.
  assert.equal(html.includes("No planned session"), true);
  assert.equal(html.includes(">Rest</span>"), false);
});

test("a backend-classified rest day keeps the definite 'Rest' label", () => {
  const plan = gapFillPlan([
    {
      date: "2026-07-07",
      countdown_label: "D-10",
      day_type: "high",
      sessions: [{ session_id: "s1", title: "Power", blocks: [] }],
    },
    {
      date: "2026-07-08",
      countdown_label: "D-9",
      day_type: "rest",
      today_card: {},
      sessions: [],
    },
  ]);

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} today={new Date(2026, 6, 7)} />);

  // The explicit rest day (day_type "rest") is a compact rest row labelled "Rest".
  assert.equal(html.includes(">Rest</span>"), true);
  assert.equal(html.includes("No planned session"), false);
});

test("gap rows are not highlighted once the plan advances to a future 'Next session'", () => {
  const plan = gapFillPlan([
    {
      date: "2026-07-07",
      countdown_label: "D-10",
      day_type: "high",
      sessions: [{ session_id: "s1", title: "Power", blocks: [] }],
    },
    {
      date: "2026-07-10",
      countdown_label: "D-7",
      day_type: "high",
      sessions: [{ session_id: "s2", title: "Conditioning", blocks: [] }],
    },
  ]);

  // Today (the 8th) is a gap day, but the view has advanced to a future session
  // (focusDay + "Next session"). The future session card owns the marker; the
  // gap row must stay plain rather than stamping today with "Next session".
  const html = renderToStaticMarkup(
    <StructuredPlanRenderer
      plan={plan}
      today={new Date(2026, 6, 8)}
      currentTrainingDayIso="2026-07-08"
      focusDay={new Date(2026, 6, 10)}
      currentDayLabel="Next session"
    />,
  );

  // No rest row carries the current-day treatment (which is also what would
  // render the marker label), so today's gap row is never stamped "Next session".
  assert.equal(html.includes("cm-rest-day cm-day-current"), false);
});

test("a synthesized rest row on the athlete's current day is highlighted", () => {
  const plan = gapFillPlan([
    {
      date: "2026-07-07",
      countdown_label: "D-10",
      day_type: "high",
      sessions: [{ session_id: "s1", title: "Power", blocks: [] }],
    },
    {
      date: "2026-07-10",
      countdown_label: "D-7",
      day_type: "high",
      sessions: [{ session_id: "s2", title: "Conditioning", blocks: [] }],
    },
  ]);

  const html = renderToStaticMarkup(
    <StructuredPlanRenderer
      plan={plan}
      today={new Date(2026, 6, 8)}
      currentTrainingDayIso="2026-07-08"
    />,
  );

  assert.equal(html.includes("cm-rest-day cm-day-current"), true);
});

// ---------------------------------------------------------------------------
// Week progression rail: equal-fill for short plans, readable scroll for long
// ones, plus the pure centring math for bringing the active week into view.

function weeksPlan(count: number, firstPhase?: string): StructuredPlan {
  return {
    schema_version: "1.0",
    plan_metadata: { title: "Fight Camp", sport: "boxing", plan_type: "fight_camp" },
    weeks: Array.from({ length: count }, (_, i) => ({
      week_id: `wk-${i + 1}`,
      week_index: i + 1,
      phase_label: i === 0 ? firstPhase ?? "GPP" : i === count - 1 ? "TAPER" : "SPP",
      days: [],
    })),
  } as unknown as StructuredPlan;
}

test("week rail fills the width without scrolling for one to four weeks", () => {
  for (const count of [1, 2, 3, 4]) {
    const html = renderToStaticMarkup(<StructuredPlanRenderer plan={weeksPlan(count)} />);
    assert.equal(
      countOccurrences(html, 'data-week-pos="'),
      count,
      `expected ${count} week cards`,
    );
    assert.equal(
      html.includes('data-scroll="true"'),
      false,
      `${count} weeks should share the width, not scroll`,
    );
  }
});

test("week rail scrolls once there are more than four weeks", () => {
  for (const count of [5, 8, 16]) {
    const html = renderToStaticMarkup(<StructuredPlanRenderer plan={weeksPlan(count)} />);
    assert.equal(
      countOccurrences(html, 'data-week-pos="'),
      count,
      `expected ${count} week cards`,
    );
    assert.equal(
      html.includes('data-scroll="true"'),
      true,
      `${count} weeks should scroll`,
    );
  }
});

test("D-10 countdown plans render a mini-title for every dated week", () => {
  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Late Fight", sport: "boxing", plan_type: "fight_camp" },
    weeks: [
      {
        week_id: "wk-1",
        week_index: 1,
        countdown_start: "D-10",
        countdown_end: "D-5",
        days: [{ date: "2026-07-27", countdown_label: "D-10", sessions: [] }],
      },
      {
        week_id: "wk-2",
        week_index: 2,
        countdown_start: "D-4",
        countdown_end: "D-0",
        days: [{ date: "2026-08-02", countdown_label: "D-4", sessions: [] }],
      },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(
    <StructuredPlanRenderer plan={plan} today={new Date(2026, 6, 27)} />,
  );

  assert.equal(countOccurrences(html, 'class="cm-week-pill-phase"'), 2);
  assert.equal(countOccurrences(html, 'title="Taper"'), 2);
  assert.equal(html.includes("Week 1 — Compressed Pre-Fight Week"), true);
});

test("next-session focus marks the active week before a dated camp starts", () => {
  const plan = {
    schema_version: "1.0",
    plan_metadata: { title: "Late Fight", sport: "boxing", plan_type: "fight_camp" },
    weeks: [
      {
        week_id: "wk-1",
        week_index: 1,
        phase_label: "SPP",
        days: [
          {
            date: "2026-07-27",
            countdown_label: "D-10",
            sessions: [{ session_id: "s1", title: "Power Transfer Touch", blocks: [] }],
          },
        ],
      },
      {
        week_id: "wk-2",
        week_index: 2,
        phase_label: "TAPER",
        days: [
          {
            date: "2026-08-03",
            countdown_label: "D-3",
            sessions: [{ session_id: "s2", title: "Primer", blocks: [] }],
          },
        ],
      },
    ],
  } satisfies StructuredPlan;

  const html = renderToStaticMarkup(
    <StructuredPlanRenderer
      plan={plan}
      today={new Date(2026, 6, 26)}
      focusDay={new Date(2026, 6, 27)}
      currentDayLabel="Next session"
    />,
  );

  assert.equal(countOccurrences(html, "cm-week-pill-current"), 1);
  assert.equal(countOccurrences(html, "cm-week-pill-dot"), 1);
  assert.equal(
    html.includes("cm-week-pill cm-week-pill-selected cm-week-pill-current"),
    true,
  );
});

test("a long phase label is kept on one line with the full text available on hover/AT", () => {
  const longPhase = "Accumulation Overreaching Realisation Block";
  const plan = weeksPlan(3, longPhase);
  const expected = formatPlanLabel(longPhase);

  const html = renderToStaticMarkup(<StructuredPlanRenderer plan={plan} />);

  // Truncation is visual (CSS ellipsis); the complete label stays in the title
  // attribute and the text node, so nothing is lost to hover or screen readers.
  assert.equal(html.includes(`title="${expected}"`), true);
  assert.equal(html.includes(`<span class="cm-week-pill-phase" title="${expected}">${expected}</span>`), true);
});

test("weekStripCenterOffset centres the active card and clamps at the start", () => {
  // Mid-rail card is centred within the viewport width.
  assert.equal(weekStripCenterOffset(300, 500, 80), 500 - (300 - 80) / 2);
  // A card near the start never produces a negative scroll offset.
  assert.equal(weekStripCenterOffset(300, 10, 80), 0);
  // The very first card sits flush at 0.
  assert.equal(weekStripCenterOffset(300, 0, 80), 0);
});
