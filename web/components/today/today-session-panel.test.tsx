import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { window as domWindow } from "../test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";

import { ToastProvider } from "@/components/toast-provider";
import { AuthProvider, AppSessionContext } from "@/components/auth-provider";
import { TodaySessionBlocks, TodaySessionPanel } from "./today-session-panel";
import { resolveCurrentDay, resolveTrainingDay, toISODate } from "@/lib/camp-map";
import type { StructuredPlan, TodayCommandView } from "@/lib/types";
import { buildTimerItems } from "@/lib/session-timer/plan";
import { createTimerState, endSession } from "@/lib/session-timer/engine";

test("weekday fallback never presents a stale template date as today", () => {
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
            date: "2026-06-13",
            weekday: "Sat",
            sessions: [{ session_id: "sat-strength", title: "Saturday strength", blocks: [] }],
          },
        ],
      },
    ],
  } satisfies StructuredPlan;

  const current = resolveCurrentDay(plan, new Date(2026, 6, 18), {
    openWeekNumber: 2,
    allowDatedWeekdayMatch: true,
  });
  const html = renderToStaticMarkup(<TodaySessionBlocks current={current} />);

  assert.equal(current.matchType, "weekday");
  assert.equal(current.trainingDayISO, "2026-07-18");
  assert.equal(html.includes("Sat 18 Jul 2026"), true);
  assert.equal(html.includes("Sat 13 Jun 2026"), false);
  assert.equal(html.includes("2026-06-13"), false);
});

test("today shows no session blocks while the plan's block has not started", () => {
  const plan = {
    schema_version: "text-adapter.v1",
    plan_metadata: { title: "Open plan", plan_type: "open_ongoing_system" },
    weeks: [
      {
        week_id: "week-1",
        week_index: 1,
        days: [
          {
            date: "2026-08-08",
            weekday: "Sat",
            sessions: [{ session_id: "sat-strength", title: "Saturday strength", blocks: [] }],
          },
        ],
      },
    ],
  } satisfies StructuredPlan;

  // Saturday 1 August, a week before the block's Saturday. Today is not a plan
  // day yet, so no future session may be presented as today's work.
  const current = resolveCurrentDay(plan, new Date(2026, 7, 1), {
    openWeekNumber: 1,
    allowDatedWeekdayMatch: true,
  });
  const html = renderToStaticMarkup(<TodaySessionBlocks current={current} />);

  assert.equal(current.inRange, false);
  assert.equal(current.matchType, null);
  assert.equal(html.includes("Saturday strength"), false);
});

test("Today uses its parent heading and starts video exercises as compact rows", () => {
  const plan = {
    weeks: [{
      week_index: 1,
      days: [{
        date: "2026-09-29",
        weekday: "Tue",
        sessions: [{
          session_id: "strength-1",
          title: "Lower-body strength",
          session_type: "strength_power",
          blocks: [{ block_id: "rdl-db", block_type: "strength", display_name: "Romanian Deadlift (DB)", sets: 3, reps: "8–12" }],
        }],
      }],
    }],
  } as StructuredPlan;
  const current = resolveCurrentDay(plan, new Date(2026, 8, 29));
  const exerciseMedia = {
    "Romanian Deadlift (DB)": { provider: "youtube" as const, video_id: "hQgFixeXdZo", start_s: 27, end_s: 49, source: "curated" as const },
  };
  const html = renderToStaticMarkup(
    <TodaySessionBlocks current={current} headline="Lower-body strength" exerciseMedia={exerciseMedia} />,
  );

  assert.doesNotMatch(html, /class="sp-session-title"/);
  assert.match(html, /Romanian Deadlift \(DB\)/);
  assert.match(html, /aria-expanded="false"/);
  assert.match(html, /class="ex-row-thumb"/);
  assert.doesNotMatch(html, /class="ex-demo"/);

  const alternateHeadline = renderToStaticMarkup(
    <TodaySessionBlocks current={current} headline="Hard sparring" exerciseMedia={exerciseMedia} />,
  );
  assert.match(alternateHeadline, /class="sp-session-title">Lower-body strength/);
});

test("a light-combat session under Today's Technical Combat heading drops its repeated title", () => {
  const plan = {
    weeks: [{
      week_index: 1,
      days: [{
        date: "2026-09-29",
        weekday: "Tue",
        sessions: [{
          session_id: "light-combat-1",
          title: "Light technical combat",
          session_type: "skill",
          blocks: [],
        }],
      }],
    }],
  } as StructuredPlan;
  const current = resolveCurrentDay(plan, new Date(2026, 8, 29));
  const html = renderToStaticMarkup(
    <TodaySessionBlocks current={current} headline="Technical Combat" />,
  );

  assert.doesNotMatch(html, /class="sp-session-title"/);
  assert.doesNotMatch(html, /light (?:technical )?(?:combat|sparring)/i);
  assert.match(html, /Pads, drills, movement or other lower-intensity combat work\./);
});

test("Today blocks omit a coach title supplied by their parent but keep its context", () => {
  const plan = {
    weeks: [{
      week_index: 1,
      days: [{
        date: "2026-09-29",
        weekday: "Tue",
        today_card: { coach_led_contact: "Light Combat / Technical" },
        sessions: [{ session_id: "throw-1", title: "Med-Ball Rotational Throw", blocks: [] }],
      }],
    }],
  } as StructuredPlan;
  const current = resolveCurrentDay(plan, new Date(2026, 8, 29));
  const html = renderToStaticMarkup(
    <TodaySessionBlocks current={current} headline="Technical Combat" />,
  );

  assert.equal((html.match(/Technical Combat/g) ?? []).length, 0);
  assert.equal(html.match(/Med-Ball Rotational Throw/g)?.length, 1);
  assert.match(html, /Pads, drills, movement or other lower-intensity combat work\./);
});

// Session timing is settled by today_service.build_today_command_view and
// carried in session_scope. These two tests pin that the panel follows it in
// both directions rather than re-deciding the day from calendar_date — the
// second-guessing that let Overview and Today describe the same payload
// differently. The backend refuses to scope a future open-plan row to today
// (tests/test_open_plan_recurring_resolution.py) and rejects a completion
// written against one with a 409, so that guard lives there, once.
test("a session the backend scopes to next stays a locked preview", () => {
  const state: TodayCommandView = {
    active_plan: { id: "plan-1", name: "Open plan", phase: "GPP" },
    today: {
      training_day: "2026-08-01",
      recommendation_state: "not_checked_in",
      decision_tier: "not_checked_in",
      warnings: [],
      next_session: {
        session_id: "2026-08-08",
        title: "Fight-Pace Conditioning and Neural Primer",
        calendar_date: "2026-08-08",
        session_relation: "today",
        effective_load: "technical",
      },
      session_scope: "next",
      session_label: "Next session",
      completion_status: "not_started",
    },
    risk_watch: [],
    open_injuries: [],
    week_summary: {},
    quick_actions: [],
  };

  const html = renderToStaticMarkup(
    <ToastProvider>
      <TodaySessionPanel
        state={state}
        structuredPlan={null}
        token="token"
        onRefresh={async () => {}}
      />
    </ToastProvider>,
  );

  assert.match(html, /Next session/);
  assert.match(html, /Sat 08 Aug 2026/);
  assert.match(html, /Check in on the day to unlock this session/);
  assert.doesNotMatch(html, />Start session<|>Skip session<|>Mark skipped</);
});

test("today's session actions stay locked until check-in is submitted", () => {
  const state: TodayCommandView = {
    active_plan: { id: "plan-1", name: "Camp", phase: "GPP" },
    today: {
      training_day: "2026-08-01",
      recommendation_state: "not_checked_in",
      decision_tier: "not_checked_in",
      warnings: [],
      next_session: {
        session_id: "session-1",
        title: "Turkish Get-Up Skill Flow",
        session_relation: "today",
        effective_load: "technical",
      },
      session_scope: "today",
      session_label: "Today's session",
      completion_status: "not_started",
    },
    risk_watch: [],
    open_injuries: [],
    week_summary: {},
    quick_actions: [],
  };

  const html = renderToStaticMarkup(
    <ToastProvider>
      <TodaySessionPanel
        state={state}
        structuredPlan={null}
        token="token"
        onRefresh={async () => {}}
      />
    </ToastProvider>,
  );

  assert.match(html, /Submit today&#x27;s check-in to unlock session actions\./);
  assert.doesNotMatch(html, />Start session<|>Skip session<|>Mark skipped</);
});

test("a session the backend scopes to today unlocks on that scope alone", () => {
  const state: TodayCommandView = {
    active_plan: { id: "plan-1", name: "Active fight camp", phase: "GPP" },
    today: {
      training_day: "2026-09-13",
      recommendation_state: "train_as_planned",
      decision_tier: "green",
      warnings: [],
      next_session: {
        session_id: "2026-09-13-strength",
        title: "Strength",
        // Deliberately stamped a week out: the scope decides, not this date.
        calendar_date: "2026-09-20",
        session_relation: "next",
        effective_load: "moderate",
      },
      session_scope: "today",
      session_label: "Today's session",
      completion_status: "not_started",
    },
    risk_watch: [],
    open_injuries: [],
    week_summary: {},
    quick_actions: [],
  };

  const html = renderToStaticMarkup(
    <AuthProvider>
      <ToastProvider>
        <TodaySessionPanel
          state={state}
          structuredPlan={null}
          token="token"
          onRefresh={async () => {}}
        />
      </ToastProvider>
    </AuthProvider>,
  );

  assert.match(html, /Today&#x27;s session/);
  assert.match(html, />Start session</);
  assert.match(html, />Skip session</);
  assert.doesNotMatch(html, /Preview only|Check in on the day/);
  assert.match(html, /class="today-session-summary"/);
  assert.ok(html.indexOf(">Start session</") < html.indexOf('class="today-session-summary"'));
});

test("safe replacement renders without blocked terminal or completion controls", () => {
  const state: TodayCommandView = {
    active_plan: { id: "plan-1", name: "Camp", phase: "SPP" },
    today: {
      training_day: "2026-08-01",
      recommendation_state: "not_checked_in",
      decision_tier: "stop",
      warnings: [],
      next_session: {
        session_id: "session-1",
        title: "Hard sparring",
        effective_load: "hard",
      },
      session_scope: "today",
      session_label: "Today",
      completion_status: "not_started",
    },
    risk_watch: [],
    open_injuries: [
      {
        id: "injury-1",
        athlete_id: "athlete-1",
        source: "today",
        body_area: "knee",
        description: "Left knee",
        severity: "severe",
        status: "open",
        created_at: "2026-08-01T08:00:00Z",
        updated_at: "2026-08-01T08:00:00Z",
      },
    ],
    week_summary: {},
    quick_actions: [],
  };
  const html = renderToStaticMarkup(
    <ToastProvider>
      <TodaySessionPanel
        state={state}
        structuredPlan={null}
        token="token"
        onRefresh={async () => {}}
      />
    </ToastProvider>,
  );

  assert.match(html, /Rest and recover/i);
  assert.doesNotMatch(html, /Blocked by an active severe injury/);
  assert.doesNotMatch(html, />Start session<|>Resume session<|Log as|>Mark done<|>Mark modified</);
});

function contactDayState(decisionTier: TodayCommandView["today"]["decision_tier"]): TodayCommandView {
  return {
    active_plan: { id: "plan-1", name: "Camp", phase: "SPP" },
    today: {
      training_day: "2026-09-25",
      recommendation_state: decisionTier === "not_checked_in" ? "not_checked_in" : "train_as_planned",
      decision_tier: decisionTier,
      warnings: [],
      next_session: {
        session_id: "2026-09-25-flush",
        title: "Mobility flush",
        calendar_date: "2026-09-25",
        session_relation: "today",
        effective_load: "low",
        coach_led_contact: "Hard sparring (coach-led)",
      },
      session_scope: "today",
      session_label: "Today's session",
      completion_status: "not_started",
    },
    risk_watch: [],
    open_injuries: [],
    week_summary: {},
    quick_actions: [],
  };
}

function renderPanel(state: TodayCommandView): string {
  return renderToStaticMarkup(
    <AuthProvider>
      <ToastProvider>
        <TodaySessionPanel state={state} structuredPlan={null} token="token" onRefresh={async () => {}} />
      </ToastProvider>
    </AuthProvider>,
  );
}

for (const level of ["rehab_only", "train_no_contact"] as const) {
  for (const status of ["not_started", "started"] as const) {
    test(`zero-load tactical watch ${status} remains actionable under ${level} while sparring stays locked`, () => {
      const state = contactDayState("green");
      state.today.completion_status = status;
      state.today.next_session = { ...state.today.next_session, title: "Tactical Watch" };
      state.effective_clinician_clearance = { level,
        scopes: level === "rehab_only" ? ["rehab"] : ["rehab", "training"], requires_update: false, limited_by: [] };
      state.live_prescription = { revision: "a".repeat(64), frozen: status === "started", safety_hold: false,
        changes: [{ action: "held", reason: "clinician_clearance_ceiling" }],
        session: { session_id: state.today.next_session.session_id!, session_type: "skill", title: "Tactical Watch",
          blocks: [{ block_id: "watch", block_type: "mindset", display_name: "Sparring exchange review" }] } };
      const html = renderPanel(state);
      assert.match(html, /Sparring exchange review/);
      assert.match(html, /Sparring rounds locked by clinician clearance/);
      // Nothing to time: a started session leads with logging it, and there is
      // no separate done / modified pick.
      assert.match(html, status === "not_started" ? />Start session</ : /class="cta"[^>]*>(<svg[\s\S]*?<\/svg>)?Finish session</);
      assert.doesNotMatch(html, /data-value="done"|data-value="modified"|>Resume session</);
      assert.doesNotMatch(html, />Start hard sparring</);
    });
  }
}

for (const tier of ["green", "modify", "pull_back", "stop", "not_checked_in"] as const) {
  test(`frozen contact renders the backend ${tier} gate despite full clinician clearance`, () => {
    const state = contactDayState(tier);
    state.today.completion_status = "started";
    state.today.next_session = { ...state.today.next_session, title: "Hard sparring", coach_led_contact: "Hard sparring" };
    state.effective_clinician_clearance = { level: "train_contact", scopes: ["rehab", "training", "contact"],
      requires_update: false, limited_by: [] };
    state.live_prescription = { revision: "a".repeat(64), frozen: true,
      safety_hold: false, changes: [],
      session: { session_id: state.today.next_session.session_id!, title: "Hard sparring", session_type: "sparring",
        blocks: [{ block_id: "contact", block_type: "sparring", display_name: "Accepted sparring" }] } };
    const html = renderPanel(state);
    if (tier === "green" || tier === "modify") {
      assert.match(html, />Resume session<|Sparring rounds<\/button>/);
      assert.match(html, />Finish session</);
    } else {
      assert.doesNotMatch(html, />Resume session<|>Start session<|>Start hard sparring<|>Finish session<|Sparring rounds<\/button>/);
    }
    assert.doesNotMatch(html, /locked by clinician clearance/);
  });
}

for (const sessionType of ["sparring", "mindset", "rehab"] as const) {
  for (const tier of ["green", "stop"] as const) {
    test(`medical hold locks ${sessionType} under ${tier} despite full contact clearance`, () => {
      const state = contactDayState(tier);
      state.today.completion_status = "started";
      state.today.recommendation_state = "pull_back";
      state.today.recommendation_reason = "No training today.\nYour current injury report includes dizziness.\nStop training and seek medical advice.";
      state.effective_clinician_clearance = { level: "train_contact", scopes: ["rehab", "training", "contact"],
        requires_update: false, limited_by: [] };
      state.live_prescription = { revision: "a".repeat(64), frozen: true, safety_hold: true,
        safety_hold_reason: state.today.recommendation_reason, changes: [],
        session: { session_id: state.today.next_session!.session_id!, title: "Accepted work", session_type: sessionType,
          blocks: [{ block_id: "work", block_type: sessionType, display_name: "Accepted work" }] } };
      const html = renderPanel(state);
      assert.doesNotMatch(html, />Resume session<|>Start session<|>Start hard sparring<|>Finish session<|Sparring rounds<\/button>/);
      assert.doesNotMatch(html, /locked by clinician clearance/);
      assert.match(html, /dizziness|medical advice/);
    });
  }
}

test("a declared sparring day leads with the sparring, with the app work alongside", () => {
  const html = renderPanel(contactDayState("green"));
  // The athlete's gym day owns the headline; the app session is named under it.
  assert.match(html, /<h2 id="today-session-heading">Hard sparring<\/h2>/);
  assert.match(html, /Also today<\/span> Mobility flush/);
  // The sparring rounds are the primary button, the app session its own start.
  assert.match(
    html,
    /today-action-tray[\s\S]*class="cta"[^>]*>Start hard sparring<[\s\S]*class="secondary-button"[^>]*>Start Mobility flush</,
  );
  // The planned rounds cover timing, so no blank timer beside them.
  assert.doesNotMatch(html, /<\/svg>Free timer<\/button>/);
  // The lead button already starts the rounds, so no duplicate shortcut.
  assert.doesNotMatch(html, /<\/svg>Sparring rounds<\/button>/);
  assert.doesNotMatch(html, /completion is unavailable|nothing to log/);
});

test("a sparring-only day is one session: the lead button starts and logs it", () => {
  const state = contactDayState("green");
  state.today.next_session = {
    ...state.today.next_session,
    session_id: "2026-09-25",
    title: "Hard sparring",
    coach_led_contact: "Hard sparring",
  };
  const html = renderPanel(state);
  assert.match(html, /<h2 id="today-session-heading">Hard sparring<\/h2>/);
  assert.match(html, />Start hard sparring</);
  assert.doesNotMatch(html, /Also today|>Start session<|>Start Hard sparring</);
  assert.match(html, />Skip session</);
});

// A declared Light Combat day only tells the app the slot is technical work; it
// never knows how light the gym runs it, so Today never calls it "light".
const LIGHT_WORDING = /light (?:technical )?(?:combat|sparring)/i;

test("a declared Light Combat day reads as Technical Combat, with the app work alongside", () => {
  const state = contactDayState("green");
  state.today.next_session = { ...state.today.next_session, coach_led_contact: "Light Combat / Technical" };
  const html = renderPanel(state);
  assert.match(html, /<h2 id="today-session-heading">Technical Combat<\/h2>/);
  assert.match(html, /Also today<\/span> Mobility flush/);
  assert.match(html, />Start technical combat</);
  assert.doesNotMatch(html, LIGHT_WORDING);
});

test("a Light Combat-only day is one Technical Combat session", () => {
  const state = contactDayState("green");
  state.today.next_session = {
    ...state.today.next_session,
    session_id: "2026-09-25",
    title: "Light Combat / Technical",
    coach_led_contact: "Light Combat / Technical",
  };
  const html = renderPanel(state);
  assert.match(html, /<h2 id="today-session-heading">Technical Combat<\/h2>/);
  assert.match(html, />Start technical combat</);
  assert.doesNotMatch(html, /Also today|>Start session</);
  assert.doesNotMatch(html, LIGHT_WORDING);
});

test("an app session titled as light combat is headlined Technical Combat", () => {
  const state = contactDayState("green");
  state.today.next_session = {
    ...state.today.next_session,
    title: "Light technical combat",
    coach_led_contact: undefined,
  };
  const html = renderPanel(state);
  assert.match(html, /<h2 id="today-session-heading">Technical Combat<\/h2>/);
  assert.doesNotMatch(html, LIGHT_WORDING);
});

test("an idless day falls back to honest copy instead of a dead end", () => {
  const state = contactDayState("green");
  state.today.next_session = { ...state.today.next_session, session_id: undefined, coach_led_contact: undefined };
  const html = renderPanel(state);
  assert.match(html, /This entry has nothing to log/);
  assert.doesNotMatch(html, /completion is unavailable for this entry/);
});

test("sparring rounds stay locked until check-in, and are never offered under a stop", () => {
  const state = contactDayState("not_checked_in");
  state.effective_clinician_clearance = { level: "train_contact", scopes: ["rehab", "training", "contact"],
    requires_update: false, limited_by: [] };
  const unchecked = renderPanel(state);
  assert.doesNotMatch(unchecked, /Sparring rounds<\/button>/);
  assert.match(unchecked, /Sparring rounds unlock after check-in/);
  assert.doesNotMatch(unchecked, /locked by clinician clearance/);
  // With the planned rounds locked, the blank timer is the way to time anything.
  assert.match(unchecked, /<\/svg>Free timer<\/button>/);

  const stopped = renderPanel(contactDayState("stop"));
  assert.doesNotMatch(stopped, /Sparring rounds<\/button>/);
  assert.doesNotMatch(stopped, /Free timer<\/button>/);
});

for (const level of ["rehab_only", "train_no_contact"] as const) {
  for (const tier of ["not_checked_in", "green"] as const) {
    for (const contactOnly of [false, true]) {
      test(`${level} contact lock copy outranks ${tier} for ${contactOnly ? "contact-owned" : "mixed camp"} sessions`, () => {
        const state = contactDayState(tier);
        if (contactOnly) state.today.next_session = { ...state.today.next_session, title: "Hard sparring", coach_led_contact: "Hard sparring" };
        state.effective_clinician_clearance = { level, scopes: level === "rehab_only" ? ["rehab"] : ["rehab", "training"],
          requires_update: false, limited_by: [{ injury_id: "chest", injury_episode_id: "episode", label: "Chest strain" }] };
        const html = renderPanel(state);
        assert.match(html, /Sparring rounds locked by clinician clearance/);
        assert.doesNotMatch(html, /Sparring rounds unlock after check-in|>Start hard sparring<|Sparring rounds<\/button>/);
      });
    }
  }
}

function nextContactDayState(): TodayCommandView {
  const state = contactDayState("green");
  state.today.next_session = {
    session_id: "2026-09-27-breathing",
    title: "Breathing Reset",
    calendar_date: "2026-09-27",
    session_relation: "next",
    effective_load: "low",
    coach_led_contact: "Hard sparring",
  };
  state.today.session_scope = "next";
  state.today.session_label = "Next session";
  return state;
}

test("a next session on a declared sparring day is headlined by the sparring", () => {
  const html = renderPanel(nextContactDayState());
  assert.match(html, /Next session/);
  assert.match(html, /<h2 id="today-session-heading">Hard sparring<\/h2>/);
  assert.match(html, /Also that day<\/span> Breathing Reset/);
  // Preview only: nothing about tomorrow's contact can be started today.
  assert.doesNotMatch(html, />Start hard sparring<|>Start session</);
});

test("completed training previews the next main session instead of leading optional visualisation", () => {
  const state = nextContactDayState();
  state.today.completion_status = "done";
  state.today.next_session = { session_id: "next-strength", title: "Strength", calendar_date: "2026-09-27",
    session_relation: "next", effective_load: "moderate" };
  const structuredPlan = { weeks: [{ week_index: 1, days: [{ date: "2026-09-27", weekday: "Sun", countdown_label: "D-20",
    today_card: { headline: "Strength" }, sessions: [
      { session_id: "optional-visualisation", title: "Fight Visualisation", optional: true,
        blocks: [{ block_type: "mindset", display_name: "Tactical Picture" }] },
      { session_id: "next-strength", title: "Strength", blocks: [{ block_type: "strength", display_name: "Squat", sets: 3, reps: 5 }] },
    ] }] }] } as StructuredPlan;
  const html = renderToStaticMarkup(<ToastProvider><TodaySessionPanel state={state}
    structuredPlan={structuredPlan} token="token" onRefresh={async () => {}} /></ToastProvider>);
  assert.match(html, /Next session/);
  assert.match(html, /<h2 id="today-session-heading">Strength<\/h2>/);
  assert.match(html, /Sun 27 Sept? 2026/);
  assert.doesNotMatch(html, />Start session<|>Mark done</);
});

test("a next sparring day read from the plan card is headlined by the sparring", () => {
  const state = nextContactDayState();
  state.today.next_session = { ...state.today.next_session, coach_led_contact: undefined };
  const structuredPlan = {
    weeks: [
      {
        week_index: 1,
        days: [
          {
            date: "2026-09-27",
            weekday: "Sun",
            countdown_label: "D-20",
            day_type: "high",
            today_card: { headline: "Breathing Reset", coach_led_contact: "Hard sparring" },
            sessions: [{ session_id: "2026-09-27-breathing", title: "Breathing Reset", blocks: [] }],
          },
        ],
      },
    ],
  } as unknown as StructuredPlan;
  const html = renderToStaticMarkup(
    <AuthProvider>
      <ToastProvider>
        <TodaySessionPanel state={state} structuredPlan={structuredPlan} token="token" onRefresh={async () => {}} />
      </ToastProvider>
    </AuthProvider>,
  );
  assert.match(html, /<h2 id="today-session-heading">Hard sparring<\/h2>/);
  assert.doesNotMatch(html, /Also that day/);
  assert.equal(html.match(/Hard sparring/g)?.length, 1);
  assert.equal(html.match(/Breathing Reset/g)?.length, 1);
});

test("a pull-back day never headlines the sparring it blocks", () => {
  const html = renderPanel(contactDayState("pull_back"));
  assert.doesNotMatch(html, /<h2 id="today-session-heading">Hard sparring<\/h2>/);
  assert.doesNotMatch(html, />Start hard sparring</);
  assert.match(html, /<h2 id="today-session-heading">Mobility flush<\/h2>/);
});

function reviewedSessionState(held: boolean): TodayCommandView {
  return {
    active_plan: { id: "plan-1", name: "Camp", phase: "SPP" },
    today: {
      training_day: "2026-08-01", recommendation_state: "pull_back", decision_tier: "pull_back", warnings: [],
      next_session: { session_id: "rehab-2026-08-01", title: "Today's rehab", session_relation: "today", effective_load: "technical" },
      session_scope: "today", session_label: "Today's session", completion_status: held ? "started" : "not_started",
    },
    live_prescription: {
      revision: "a".repeat(64), safety_hold: held, frozen: held, changes: [{ action: "held" }],
      session: { session_id: "rehab-2026-08-01", title: "Today's rehab", session_type: "rehab",
        blocks: [{ block_id: "reviewed-1", block_type: "rehab", display_name: "Reviewed test rehab" }] },
    },
    risk_watch: [], open_injuries: [], week_summary: {}, quick_actions: [],
  };
}

test("reviewed rehab remains available under reduced readiness and uses server blocks", () => {
  const state = reviewedSessionState(false);
  const html = renderToStaticMarkup(<AuthProvider><ToastProvider><TodaySessionPanel state={state} structuredPlan={null} token="token" onRefresh={async () => {}} /></ToastProvider></AuthProvider>);
  assert.match(html, /Reviewed test rehab/);
  assert.match(html, />Start session</);
  assert.doesNotMatch(html, /Do not start this session/);
});

function guidanceDayState(): TodayCommandView {
  const state = reviewedSessionState(false);
  state.today.recommendation_state = "train_as_planned";
  state.today.decision_tier = "green";
  state.live_prescription!.changes = [];
  state.live_prescription!.session.blocks = [{
    block_id: "rehab:chest", block_type: "rehab", display_name: "Chest strain recovery support", is_loading: false,
    coaching_cues: ["Rest from exercise that loads it. Use comfortable everyday movement."],
    drill_snapshot: { rehab_stage: "calm", function: "recovery_downregulation", dose: {} },
  }];
  return state;
}

test("calm-stage guidance is checked off, never started", () => {
  const html = renderToStaticMarkup(<AuthProvider><ToastProvider><TodaySessionPanel state={guidanceDayState()} structuredPlan={null} token="token" onRefresh={async () => {}} /></ToastProvider></AuthProvider>);
  assert.match(html, /Chest strain recovery support/);
  assert.match(html, /No rehab exercises at this stage/);
  assert.match(html, />Followed it</);
  assert.doesNotMatch(html, />Start session<|>Skip session<|How much rehab did you do/);
});

test("checking off guidance saves it as followed and asks how it felt", async () => {
  const container = document.createElement("div"); document.body.appendChild(container);
  const root = createRoot(container);
  const original = globalThis.fetch;
  const calls: Array<Record<string, unknown>> = [];
  globalThis.fetch = (async (_input, init) => {
    if (init?.method === "POST") {
      calls.push(JSON.parse(String(init.body)));
      return new Response(JSON.stringify({ completion: { id: "completion-1", plan_id: "plan-1", session_id: "rehab-2026-08-01", training_day: "2026-08-01" },
        rehab_response_prompts: [{ injury_id: "injury-1", injury_episode_id: "episode-1", injury_label: "Chest", body_region: "chest", side: "unknown",
          during_question: "How did it feel during the rehab work?", during_options: ["better", "same", "worse", "not_sure"],
          limit_question: "Did you have to reduce or stop because of it?", limit_options: ["no", "reduced", "stopped"] }] }), { status: 200 });
    }
    return new Response('{"response_sets":[],"history_truncated":false}', { status: 200 });
  }) as typeof fetch;
  try {
    await act(async () => { root.render(<AuthProvider><ToastProvider><TodaySessionPanel state={guidanceDayState()} structuredPlan={null} token="token" onRefresh={async () => {}} /></ToastProvider></AuthProvider>); });
    const button = Array.from(container.querySelectorAll("button")).find(b => b.textContent?.trim() === "Followed it");
    assert.ok(button);
    await act(async () => { button.dispatchEvent(new domWindow.MouseEvent("click", { bubbles: true })); });
    assert.equal(calls.length, 1);
    assert.equal(calls[0].status, "done");
    assert.equal(calls[0].rehab_performance, "done_as_shown");
    assert.match(container.textContent ?? "", /How did it feel today\?/);
    assert.match(container.textContent ?? "", /while following the guidance/);
    assert.doesNotMatch(container.textContent ?? "", /How did the rehab work go|during the rehab work/);
  } finally { globalThis.fetch = original; act(() => root.unmount()); container.remove(); }
});

test("a new safety hold offers stopped logging without resuming frozen work", () => {
  const state = reviewedSessionState(true);
  const html = renderToStaticMarkup(<AuthProvider><ToastProvider><TodaySessionPanel state={state} structuredPlan={null} token="token" onRefresh={async () => {}} /></ToastProvider></AuthProvider>);
  assert.match(html, /Reviewed test rehab/);
  assert.match(html, />Log stopped session</);
  assert.match(html, />Mark skipped</);
  assert.doesNotMatch(html, />Start session<|>Done<|>Resume session<|>Finish session</);
});

for (const [value, label] of [
  ["done_as_shown", "Done as shown"], ["changed", "Changed it"], ["stopped", "Stopped early"],
] as const) {
  test(`rehab completion selects and submits ${value}`, async () => {
    const container = document.createElement("div"); document.body.appendChild(container);
    const root = createRoot(container);
    const state = reviewedSessionState(false);
    state.today.completion_status = "started";
    const original = globalThis.fetch;
    const calls: Array<Record<string, unknown>> = [];
    let refreshes = 0;
    globalThis.fetch = (async (_input, init) => {
      if (init?.method === "POST") {
        calls.push(JSON.parse(String(init.body)));
        return new Response(JSON.stringify({ completion: { id: "completion-1" }, rehab_response_prompts: [] }), { status: 200 });
      }
      return new Response('{"response_sets":[],"history_truncated":false}', { status: 200 });
    }) as typeof fetch;
    async function click(label: string) {
      const button = Array.from(container.querySelectorAll("button")).find(b => b.textContent?.trim() === label);
      assert.ok(button, label);
      await act(async () => { button.dispatchEvent(new domWindow.MouseEvent("click", { bubbles: true })); });
    }
    try {
      await act(async () => { root.render(<AuthProvider><ToastProvider><TodaySessionPanel state={state} structuredPlan={null} token="token" onRefresh={async () => { refreshes++; }} /></ToastProvider></AuthProvider>); });
      await click("Finish session");
      // The review sheet is portalled to the body: rehab alone owes no exercise
      // ticks, so the session reads as done and asks for the rehab amount.
      const sheet = document.querySelector<HTMLElement>(".today-review-root");
      assert.ok(sheet);
      const save = Array.from(sheet.querySelectorAll("button")).find((b) => b.textContent?.trim() === "Save session");
      assert.ok(save);
      assert.equal(save.className, "cta");
      // Fill the existing required review field before choosing rehab performance.
      const effort = sheet.querySelector<HTMLInputElement>('input[aria-label="Session effort"]');
      assert.ok(effort);
      await act(async () => { effort.dispatchEvent(new domWindow.MouseEvent("click", { bubbles: true })); });
      await act(async () => { save.dispatchEvent(new domWindow.MouseEvent("click", { bubbles: true })); });
      assert.equal(calls.length, 0);
      assert.match(sheet.textContent ?? "", /Choose how much rehab you performed/);
      const group = sheet.querySelector('[aria-label="How much rehab did you do?"]');
      assert.ok(group);
      const option = Array.from(group.querySelectorAll("button")).find((b) => b.textContent?.trim() === label);
      assert.ok(option);
      await act(async () => { option.dispatchEvent(new domWindow.MouseEvent("click", { bubbles: true })); });
      for (const button of group.querySelectorAll("button")) {
        assert.ok(button.classList.contains("today-segment"));
        assert.equal(button.classList.contains("today-segment-active"), button.textContent === label);
        assert.equal(button.getAttribute("aria-pressed"), String(button.textContent === label));
      }
      await act(async () => { save.dispatchEvent(new domWindow.MouseEvent("click", { bubbles: true })); });
      assert.equal(calls.length, 1);
      assert.equal(calls[0].rehab_performance, value);
      assert.equal(calls[0].status, "done");
      assert.equal(calls[0].session_rpe, 5);
      assert.equal(refreshes, 1);
    } finally { globalThis.fetch = original; act(() => root.unmount()); container.remove(); }
  });
}

test("one live rehab session renders every reviewed bundle drill", () => {
  const state = contactDayState("green");
  state.today.next_session = {
    session_id: "rehab-2026-09-25", title: "Today's rehab", session_relation: "today",
  };
  state.live_prescription = {
    revision: "a".repeat(64),
    safety_hold: false, frozen: false, changes: [],
    session: {
      session_id: "rehab-2026-09-25", title: "Today's rehab", session_type: "rehab",
      blocks: [
        { block_id: "rehab:injury-1:balance", block_type: "rehab",
          display_name: "Reviewed supported balance", coaching_cues: ["Use a stable counter."] },
        { block_id: "rehab:injury-1:lowering", block_type: "rehab",
          display_name: "Reviewed heel lowering", coaching_cues: ["Lower within comfort."] },
      ],
    },
  };
  const html = renderPanel(state);
  assert.match(html, /Reviewed supported balance/);
  assert.match(html, /Reviewed heel lowering/);
  assert.equal((html.match(/>Start session</g) ?? []).length, 1);
});

test("contact actions respect live holds and reviewed rehab replacements", () => {
  for (const rehabOnly of [false, true]) {
    const state = contactDayState("green");
    state.live_prescription = {
      revision: "a".repeat(64), frozen: false, safety_hold: !rehabOnly, rehab_only: rehabOnly,
      changes: [{ action: "held", reason: "clinician_clearance_ceiling" }],
      session: { session_id: rehabOnly ? "rehab-2026-09-25" : "2026-09-25-flush", title: rehabOnly ? "Today's rehab" : "Mobility flush",
        session_type: rehabOnly ? "rehab" : "strength", blocks: [] },
    };
    const html = renderPanel(state);
    assert.doesNotMatch(html, />Start hard sparring<|<h2 id="today-session-heading">Hard sparring<|Sparring rounds<\/button>/);
    assert.match(html, /Sparring rounds locked today/);
    if (rehabOnly) assert.match(html, />Start session</);
  }
});

for (const level of ["rehab_only", "train_no_contact"] as const) {
  test(`${level} effective clearance locks contact even when the original plan permits it`, () => {
    const state = contactDayState("green");
    state.effective_clinician_clearance = { level, scopes: level === "rehab_only" ? ["rehab"] : ["rehab", "training"],
      requires_update: false, limited_by: [{ injury_id: "chest", injury_episode_id: "chest-episode", label: "Chest strain" }] };
    const html = renderPanel(state);
    assert.doesNotMatch(html, />Start hard sparring<|<h2 id="today-session-heading">Hard sparring<|Sparring rounds<\/button>/);
    assert.match(html, /Sparring rounds locked by clinician clearance/);
  });
}

for (const level of ["rehab_only", "train_no_contact", "train_contact"] as const) {
  for (const status of ["not_started", "started"] as const) {
    test(`sparring-only ${status} actions obey ${level} without losing contact identity`, () => {
      const state = contactDayState("green");
      state.today.next_session = { ...state.today.next_session, session_id: "contact-only",
        title: "Hard sparring", coach_led_contact: "Hard sparring" };
      state.today.completion_status = status;
      state.effective_clinician_clearance = { level,
        scopes: level === "rehab_only" ? ["rehab"] : level === "train_no_contact" ? ["rehab", "training"] : ["rehab", "training", "contact"],
        requires_update: false, limited_by: [{ injury_id: "chest", injury_episode_id: "episode", label: "Chest strain" }] };
      const html = renderPanel(state);
      if (level === "train_contact") {
        assert.match(html, status === "not_started" ? />Start hard sparring</ : />Resume session</);
        if (status === "started") assert.match(html, />Finish session</);
        assert.doesNotMatch(html, /Sparring rounds locked by clinician clearance/);
      } else {
        assert.match(html, /Sparring rounds locked by clinician clearance/);
        assert.doesNotMatch(html, />Start session<|>Start hard sparring<|>Resume session<|>Finish session<|<form/);
      }
    });
  }
}

for (const status of ["not_started", "started"] as const) {
  test(`mixed camp ${status} keeps reviewed non-contact actions under train_no_contact`, () => {
    const state = contactDayState("green");
    state.today.completion_status = status;
    state.effective_clinician_clearance = { level: "train_no_contact", scopes: ["rehab", "training"], requires_update: false,
      limited_by: [{ injury_id: "chest", injury_episode_id: "episode", label: "Chest strain" }] };
    state.live_prescription = { revision: "a".repeat(64), frozen: status === "started", safety_hold: false, changes: [],
      session: { session_id: state.today.next_session.session_id!, session_type: "strength", title: "Mobility flush",
        blocks: [{ block_id: "safe", block_type: "strength", display_name: "Reviewed non-contact work" }] } };
    const html = renderPanel(state);
    assert.match(html, /Reviewed non-contact work/);
    assert.match(html, /Sparring rounds locked by clinician clearance/);
    assert.match(html, status === "not_started" ? />Start session</ : />Resume session</);
    if (status === "started") assert.match(html, />Finish session</);
    assert.doesNotMatch(html, />Start hard sparring</);
  });
}

for (const action of ["Finish session", "Skip session"] as const) {
  test(`lowering contact clearance closes an already open ${action} log`, async () => {
    const container = document.createElement("div"); document.body.appendChild(container);
    const root = createRoot(container);
    const state = contactDayState("green");
    state.today.next_session = { ...state.today.next_session, session_id: "contact-only", title: "Hard sparring", coach_led_contact: "Hard sparring" };
    state.today.completion_status = "started";
    state.effective_clinician_clearance = { level: "train_contact", scopes: ["rehab", "training", "contact"], requires_update: false, limited_by: [] };
    const original = globalThis.fetch;
    const writes: unknown[] = [];
    globalThis.fetch = (async (_input, init) => {
      if (init?.method === "POST") writes.push(init.body);
      return new Response('{"response_sets":[],"history_truncated":false}', { status: 200 });
    }) as typeof fetch;
    const render = () => root.render(<AuthProvider><ToastProvider><TodaySessionPanel state={state} structuredPlan={null} token="token" onRefresh={async () => {}} /></ToastProvider></AuthProvider>);
    try {
      await act(async () => { render(); });
      const choice = Array.from(container.querySelectorAll("button")).find((b) => b.textContent?.trim() === action);
      assert.ok(choice);
      await act(async () => { choice.dispatchEvent(new domWindow.MouseEvent("click", { bubbles: true })); });
      // Finish opens the session's review sheet (portalled to the body); Skip the reason form.
      const openLog = () => document.querySelector(".today-review-root") ?? container.querySelector("form");
      assert.ok(openLog());
      state.effective_clinician_clearance = { ...state.effective_clinician_clearance!, level: "train_no_contact", scopes: ["rehab", "training"] };
      await act(async () => { render(); });
      assert.equal(openLog(), null);
      assert.equal(Array.from(container.querySelectorAll("button")).find((b) => b.textContent?.trim() === "Finish session"), undefined);
      assert.match(container.textContent ?? "", /Sparring rounds locked by clinician clearance/);
      assert.equal(writes.length, 0);
    } finally { globalThis.fetch = original; act(() => root.unmount()); container.remove(); }
  });
}

test("start session runs the day's visualisation first, then hands on to the timer", async () => {
  const container = document.createElement("div"); document.body.appendChild(container);
  const root = createRoot(container);
  const state = contactDayState("green");
  state.today.next_session = { ...state.today.next_session, coach_led_contact: undefined, title: "Fight Visualisation" };
  state.live_prescription = { revision: "a".repeat(64), frozen: false, safety_hold: false, changes: [],
    session: { session_id: state.today.next_session.session_id!, session_type: "skill", title: "Fight Visualisation",
      blocks: [
        { block_id: "vis-1", block_type: "mindset", display_name: "Tactical Picture",
          coaching_cues: ["See the opponent clearly.", "Cue: Take the space."] },
        { block_id: "rdl", block_type: "strength", display_name: "Romanian Deadlift", sets: 3, reps: "8" },
      ] } };
  const original = globalThis.fetch;
  const posts: Array<Record<string, unknown>> = [];
  globalThis.fetch = (async (_input, init) => {
    if (init?.method === "POST") {
      posts.push(JSON.parse(String(init.body)));
      return new Response(JSON.stringify({ completion: { id: "completion-1" }, rehab_response_prompts: [] }), { status: 200 });
    }
    return new Response('{"response_sets":[],"history_truncated":false,"logs":[]}', { status: 200 });
  }) as typeof fetch;
  const button = (scope: ParentNode, label: string) =>
    Array.from(scope.querySelectorAll("button")).find((b) => b.textContent?.trim() === label);
  try {
    await act(async () => { root.render(<AuthProvider><ToastProvider><TodaySessionPanel state={state} structuredPlan={null} token="token" onRefresh={async () => {}} /></ToastProvider></AuthProvider>); });
    const start = button(container, "Start session");
    assert.ok(start);
    await act(async () => { start.dispatchEvent(new domWindow.MouseEvent("click", { bubbles: true })); });
    assert.equal(posts[0]?.status, "started");
    const player = document.querySelector<HTMLElement>('[aria-label="Guided Tactical Picture"]');
    assert.ok(player, "the visualisation opens first");
    assert.equal(document.querySelector(".st-root"), null);
    const skip = button(player, "Skip to training");
    assert.ok(skip);
    await act(async () => { skip.dispatchEvent(new domWindow.MouseEvent("click", { bubbles: true })); });
    assert.equal(document.querySelector('[aria-label="Guided Tactical Picture"]'), null);
    assert.ok(document.querySelector(".st-root"), "then the timer takes over");
  } finally { globalThis.fetch = original; act(() => root.unmount()); container.remove(); }
});

test("rehab replacement drops the held day's strength and combat coaching", async () => {
  const state = reviewedSessionState(false);
  state.today.training_day = toISODate(resolveTrainingDay(new Date()));
  state.live_prescription!.rehab_only = true;
  state.today.next_session!.calendar_date = state.today.training_day;
  const structuredPlan: StructuredPlan = { weeks: [{ week_id: "w", days: [{
    date: state.today.training_day, today_card: {
      headline: "Strength", coach_led_contact: "Hard sparring", primary_warning: "Push today's strength load",
      mindset_anchor: { focus_cue: "Keep a weekly power exposure" }, nutrition_summary: "Keep your normal nutrition plan",
    }, sessions: [{ session_id: "original", title: "Strength", objective: "Build structural strength" }],
  }] }] };
  const container = document.createElement("div");
  const root = createRoot(container);
  const renderPanel = (view: TodayCommandView) => (
    <AppSessionContext.Provider value={{ isReady: true, isMeHydrated: true, hasTransientMeError: false,
      session: null, me: null, previewAppearanceMode: () => {}, refreshMe: async () => {},
      replaceMe: () => {}, signOut: async () => {} }}>
      <ToastProvider><TodaySessionPanel state={view} structuredPlan={structuredPlan} token="" onRefresh={async () => {}} /></ToastProvider>
    </AppSessionContext.Provider>
  );
  try {
    const original = { ...state, live_prescription: undefined, today: { ...state.today,
      recommendation_state: "train_as_planned" as const, decision_tier: "green" as const,
      next_session: { ...state.today.next_session, session_id: "original", title: "Strength" } } };
    await act(async () => { root.render(renderPanel(original)); });
    // Prove the held day's coaching was present before the live replacement.
    assert.match(container.textContent!, /Build structural strength/);
    assert.match(container.textContent!, /weekly power exposure/);
    await act(async () => { root.render(renderPanel(state)); });
    assert.match(container.textContent!, /Reviewed test rehab/);
    assert.doesNotMatch(container.textContent!, /Hard sparring|weekly power exposure|Push today|Build structural strength/);
  } finally {
    await act(async () => { root.unmount(); });
  }
});

test("finished mixed rehab run survives a failed batch and opens populated review only after retry saves", async () => {
  const state = contactDayState("green");
  state.today.completion_status = "started";
  state.today.next_session = { ...state.today.next_session, coach_led_contact: undefined, title: "Strength and rehab" };
  const blocks = [
    { block_id: "rope", block_type: "power", display_name: "Rope", sets: 3, reps: "8" },
    { block_id: "press", block_type: "strength", display_name: "Press", sets: 3, reps: "8" },
    { block_id: "rdl", block_type: "strength", display_name: "RDL", sets: 3, reps: "8" },
    { block_id: "bike", block_type: "conditioning", display_name: "Bike", rounds: 6, work: {value: 30, unit: "seconds"} },
    { block_id: "rehab", block_type: "rehab", display_name: "Rehab hold", sets: 2, reps: "6" },
  ];
  state.live_prescription = {revision: "a".repeat(64), frozen: false, safety_hold: false, changes: [],
    session: {session_id: state.today.next_session.session_id!, session_type: "strength", title: "Strength and rehab", blocks}};
  const items = buildTimerItems([state.live_prescription.session]);
  const run = endSession({...createTimerState(items), completed: [3, 0, 1, 0, 2], index: 4}, Date.now());
  const key = `unlxck.session-timer.run:plan-1:${state.today.next_session.session_id}:${state.today.training_day}`;
  window.localStorage.setItem(key, JSON.stringify({version: 2, key, itemIds: items.map(item => `${item.kind}:${item.id}`), state: run}));
  const originalFetch = globalThis.fetch;
  const batches: Array<{ entries: Array<{ block_id: string; status: string }>; keep_existing: boolean }> = [];
  const pending: Array<(response: Response) => void> = [];
  const manual = {block_id: "press", status: "as_prescribed", actual: {load: {value: 25, unit: "kg"}}};
  globalThis.fetch = ((input: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      assert.match(String(input), /\/api\/today\/exercise-logs$/);
      batches.push(JSON.parse(String(init.body)));
      return new Promise<Response>(resolve => pending.push(resolve));
    }
    return Promise.resolve(new Response(JSON.stringify({logs: [manual], response_sets: [], history_truncated: false}), {status: 200}));
  }) as typeof fetch;
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  try {
    await act(async () => { root.render(<AuthProvider><ToastProvider><TodaySessionPanel state={state}
      structuredPlan={null} token="token" onRefresh={async () => {}} /></ToastProvider></AuthProvider>);
      await new Promise(resolve => setTimeout(resolve, 20)); });
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)); });
    assert.equal(batches.length, 1);
    assert.deepEqual(batches[0].entries.map(entry => [entry.block_id, entry.status]), [
      ["rope", "as_prescribed"], ["rdl", "modified"], ["bike", "skipped"],
    ]);
    assert.equal(batches[0].keep_existing, true);
    assert.match(container.textContent ?? "", /Save timer results/);
    assert.ok(window.localStorage.getItem(key));
    assert.equal(document.querySelector(".today-review-root"), null);
    await act(async () => { pending[0](new Response(JSON.stringify({detail: "Network write failed"}), {status: 409})); });
    assert.ok(window.localStorage.getItem(key));
    assert.equal(document.querySelector(".today-review-root"), null);
    await act(async () => { document.querySelector<HTMLButtonElement>(".st-mini")!.click(); });
    const retry = Array.from(document.querySelectorAll("button")).find(button => button.textContent === "Retry save")!;
    assert.ok(retry);
    await act(async () => { retry.click(); retry.click(); });
    assert.equal(batches.length, 2);
    assert.ok(window.localStorage.getItem(key));
    await act(async () => { pending[1](new Response(JSON.stringify({logs: batches[1].entries}), {status: 200})); });
    assert.equal(window.localStorage.getItem(key), null);
    assert.equal(document.querySelector(".st-root"), null);
    assert.match(document.querySelector(".today-review-root")?.textContent ?? "", /4 of 4 exercises logged/);
    assert.match(document.querySelector(".today-review-root")?.textContent ?? "", /How much rehab/);
  } finally {
    await act(async () => { root.unmount(); });
    container.remove();
    globalThis.fetch = originalFetch;
    window.localStorage.removeItem(key);
  }
});

test("a logged day no longer offers its sparring rounds", () => {
  for (const status of ["done", "modified", "skipped"] as const) {
    const state = contactDayState("green");
    state.today.completion_status = status;
    const html = renderPanel(state);
    assert.doesNotMatch(html, /Sparring rounds<\/button>|>Start hard sparring</);
    // With the day's rounds gone, the blank timer is back.
    assert.match(html, /<\/svg>Free timer<\/button>/);
  }
});
