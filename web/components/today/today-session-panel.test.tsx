import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { ToastProvider } from "@/components/toast-provider";
import { AuthProvider } from "@/components/auth-provider";
import { TodaySessionBlocks, TodaySessionPanel } from "./today-session-panel";
import { resolveCurrentDay } from "@/lib/camp-map";
import type { StructuredPlan, TodayCommandView } from "@/lib/types";

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
  assert.match(html, /Preview only/);
  assert.doesNotMatch(html, />Start session<|>Mark skipped</);
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
  assert.doesNotMatch(html, />Start session<|>Mark skipped</);
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
  assert.match(html, />Mark skipped</);
  assert.doesNotMatch(html, /Preview only|Check in on the day/);
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
  assert.doesNotMatch(html, />Start session<|>Mark done<|>Mark modified<|>Resume session</);
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

test("a cleared day with coach-led sparring offers Start rounds and the round timer", () => {
  const html = renderPanel(contactDayState("green"));
  assert.match(html, /Today&#x27;s contact/);
  assert.match(html, /Hard sparring \(coach-led\)/);
  assert.match(html, />Start rounds</);
  assert.match(html, />Round timer</);
});

test("sparring rounds stay locked until check-in, and are never offered under a stop", () => {
  const unchecked = renderPanel(contactDayState("not_checked_in"));
  assert.doesNotMatch(unchecked, />Start rounds</);
  assert.match(unchecked, /Check in to unlock sparring rounds/);

  const stopped = renderPanel(contactDayState("stop"));
  assert.doesNotMatch(stopped, />Start rounds</);
  assert.doesNotMatch(stopped, />Round timer</);
});
