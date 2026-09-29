import test from "node:test";
import assert from "node:assert/strict";

import { resolveTodayDecision } from "./today-authoritative.ts";
import { getTodayNextStep } from "./today-next-step.ts";
import type { TodayCommandView } from "./types.ts";

const base: TodayCommandView = {
  active_plan: { id: "plan-1", name: "Camp" },
  today: {
    training_day: "2026-06-01",
    recommendation_state: "train_as_planned",
    decision_tier: "green",
    next_session: { session_id: "s2", title: "Boxing rounds" },
    session_scope: "next",
    session_label: "Next",
    completion_status: "modified",
  },
  risk_watch: [],
  open_injuries: [],
  week_summary: {},
  quick_actions: [],
};

test("modified log previews the server-selected next session", () => {
  const result = getTodayNextStep(base, resolveTodayDecision(base));
  assert.equal(result?.title, "Adjustment logged");
  assert.equal(result?.href, "#today-session");
  assert.match(result?.detail ?? "", /Boxing rounds/);
  assert.match(result?.detail ?? "", /Check in on that training day/);
});

test("skipped log with a safety hold leads to guidance", () => {
  const state: TodayCommandView = {
    ...base,
    today: { ...base.today, completion_status: "skipped", decision_tier: "stop" },
  };
  const result = getTodayNextStep(state, resolveTodayDecision(state));
  assert.equal(result?.title, "Skip logged");
  assert.equal(result?.href, "/history");
  assert.doesNotMatch(result?.detail ?? "", /Boxing rounds/);
});

test("visible same-day safety guidance gets a direct link", () => {
  const state: TodayCommandView = {
    ...base,
    today: {
      ...base.today,
      completion_status: "skipped",
      decision_tier: "stop",
      session_scope: "today",
    },
  };
  assert.equal(getTodayNextStep(state, resolveTodayDecision(state))?.href, "#today-decision");
});

test("no next session links to the existing camp plan", () => {
  const state: TodayCommandView = {
    ...base,
    today: { ...base.today, session_scope: "none", next_session: {} },
  };
  assert.equal(getTodayNextStep(state, resolveTodayDecision(state))?.href, "/plans/plan-1");
});

test("an unlogged session shows no follow-up", () => {
  const state: TodayCommandView = {
    ...base,
    today: { ...base.today, completion_status: "started" },
  };
  assert.equal(getTodayNextStep(state, resolveTodayDecision(state)), null);
});
