import assert from "node:assert/strict";
import test from "node:test";

import { reconcileTodayWithPlanCard } from "./use-today-command";
import type {
  StructuredPlan,
  TodayCommandView,
  TodaySessionCompletionRecord,
} from "@/lib/types";

const STALE_FUTURE_STATE: TodayCommandView = {
  active_plan: {
    id: "plan-1",
    name: "Active fight camp",
    phase: "GPP",
    fight_date: "2026-10-15",
  },
  today: {
    training_day: "2026-09-13",
    recommendation_state: "train_as_planned",
    decision_tier: "green",
    next_session: {
      session_id: "hard-sparring",
      title: "Hard sparring",
      calendar_date: "2026-09-15",
      session_relation: "next",
      effective_load: "hard",
    },
    session_scope: "next",
    session_label: "Next session",
    completion_status: "not_started",
    warnings: [],
  },
  risk_watch: [],
  open_injuries: [],
  week_summary: {},
  quick_actions: [],
};

const PLAN_CARD: StructuredPlan = {
  schema_version: "text-adapter.v1",
  plan_metadata: { title: "Active fight camp" },
  weeks: [
    {
      week_id: "week-1",
      week_index: 1,
      days: [
        {
          date: "2026-09-13",
          weekday: "Sun",
          countdown_label: "D-32",
          today_card: { headline: "Strength" },
          sessions: [
            {
              session_id: "text-session-1",
              session_type: "strength",
              title: "Strength",
              objective: "Build resilient force without compromising sparring.",
              blocks: [{ block_id: "sled-push", display_name: "Sled Push (Board)" }],
            },
          ],
        },
        {
          date: "2026-09-15",
          weekday: "Tue",
          countdown_label: "D-30",
          today_card: { headline: "Hard sparring" },
          sessions: [],
        },
      ],
    },
  ],
};

const PLAN_SCHEDULE = { scheduleContext: null, createdAt: "2026-09-12T10:00:00Z" };

test("today's reconstructed plan card replaces a stale future schedule entry", () => {
  const reconciled = reconcileTodayWithPlanCard(
    STALE_FUTURE_STATE,
    PLAN_CARD,
    PLAN_SCHEDULE,
    [],
  );

  assert.equal(reconciled.today.next_session.session_id, "text-session-1");
  assert.equal(reconciled.today.next_session.title, "Strength");
  assert.equal(reconciled.today.next_session.calendar_date, "2026-09-13");
  assert.equal(reconciled.today.next_session.session_relation, "today");
  assert.equal(reconciled.today.session_scope, "today");
  assert.equal(reconciled.today.completion_status, "not_started");
});

test("today's reconstructed session restores its durable started state", () => {
  const completion: TodaySessionCompletionRecord = {
    id: "completion-1",
    athlete_id: "athlete-1",
    plan_id: "plan-1",
    session_id: "text-session-1",
    training_day: "2026-09-13",
    status: "started",
  };

  const reconciled = reconcileTodayWithPlanCard(
    STALE_FUTURE_STATE,
    PLAN_CARD,
    PLAN_SCHEDULE,
    [completion],
  );

  assert.equal(reconciled.today.next_session.session_id, "text-session-1");
  assert.equal(reconciled.today.completion_status, "started");
});

test("a completed reconstructed session advances to the next plan-card entry", () => {
  const completion: TodaySessionCompletionRecord = {
    id: "completion-1",
    athlete_id: "athlete-1",
    plan_id: "plan-1",
    session_id: "text-session-1",
    training_day: "2026-09-13",
    status: "done",
  };

  const reconciled = reconcileTodayWithPlanCard(
    STALE_FUTURE_STATE,
    PLAN_CARD,
    PLAN_SCHEDULE,
    [completion],
  );

  assert.notEqual(reconciled, STALE_FUTURE_STATE);
  assert.equal(reconciled.today.next_session.session_id, undefined);
  assert.equal(reconciled.today.next_session.title, "Hard sparring");
  assert.equal(reconciled.today.next_session.calendar_date, "2026-09-15");
  assert.equal(reconciled.today.next_session.session_relation, "next");
  assert.equal(reconciled.today.session_scope, "next");
  assert.equal(reconciled.today.session_label, "Next session");
});
