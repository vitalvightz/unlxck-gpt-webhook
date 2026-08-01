import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { ToastProvider } from "@/components/toast-provider";
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
