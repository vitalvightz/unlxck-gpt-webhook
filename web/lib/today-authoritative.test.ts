import test from "node:test";
import assert from "node:assert/strict";

import {
  getInjuryOverrideBanner,
  getTierMeta,
  getTodayDecisionBanner,
  resolveTodayDecision,
} from "./today-authoritative.ts";
import type { TodayCommandView } from "./types.ts";

const BASE_STATE: TodayCommandView = {
  active_plan: { id: "11111111-1111-1111-1111-111111111111", name: "Camp", phase: "SPP" },
  today: {
    training_day: "2026-06-18",
    recommendation_state: "train_as_planned",
    recommendation_reason: "Train as planned.",
    decision_tier: "green",
    warnings: [],
    next_session: { session_id: "session-1", title: "Boxing conditioning" },
    session_scope: "today",
    session_label: "Today",
    completion_status: "not_started",
  },
  risk_watch: [],
  open_injuries: [],
  week_summary: {},
  quick_actions: [],
};

test("green remains completable despite stop-sounding prose", () => {
  const resolved = resolveTodayDecision({
    ...BASE_STATE,
    today: {
      ...BASE_STATE.today,
      recommendation_reason: "No training today.\nRed flag detected. Seek medical advice.",
      decision_tier: "green",
    },
  });

  assert.equal(resolved.authoritativeTier, "green");
  assert.equal(resolved.blocksTraining, false);
  assert.equal(resolved.canCompleteSession, true);
  assert.ok(resolved.banner);
  assert.equal(resolved.banner.displayState, "go");
  assert.equal(resolved.banner.tone, "green");
  assert.equal("blocksTraining" in resolved.banner, false);
});

test("pull-back remains blocking despite green-sounding prose", () => {
  const resolved = resolveTodayDecision({
    ...BASE_STATE,
    today: {
      ...BASE_STATE.today,
      recommendation_state: "pull_back",
      recommendation_reason: "Sharp work ready.\nEverything feels good.\nTrain normally.",
      decision_tier: "pull_back",
    },
  });

  assert.equal(resolved.authoritativeTier, "pull_back");
  assert.equal(resolved.blocksTraining, true);
  assert.equal(resolved.canCompleteSession, false);
});

test("STOP uses a safe replacement only for today's matched session", () => {
  const resolved = resolveTodayDecision({
    ...BASE_STATE,
    today: {
      ...BASE_STATE.today,
      recommendation_state: "pull_back",
      decision_tier: "stop",
    },
  });

  assert.equal(resolved.authoritativeTier, "stop");
  assert.equal(resolved.sessionIsToday, true);
  assert.equal(resolved.blocksTraining, true);
  assert.equal(resolved.canCompleteSession, false);
  assert.equal(resolved.useSafeReplacement, true);
});

test("backend STOP remains visible before check-in when a severe injury is active", () => {
  const resolved = resolveTodayDecision({
    ...BASE_STATE,
    today: {
      ...BASE_STATE.today,
      recommendation_state: "not_checked_in",
      recommendation_reason: null,
      decision_tier: "stop",
    },
    open_injuries: [
      {
        id: "injury-1",
        athlete_id: "athlete-1",
        source: "today",
        body_area: "knee",
        description: "left knee",
        severity: "severe",
        status: "open",
        created_at: "2026-06-18T10:00:00Z",
        updated_at: "2026-06-18T10:00:00Z",
      },
    ],
  });

  assert.equal(resolved.displayTier, "stop");
  assert.ok(resolved.banner);
  assert.equal(resolved.banner.displayState, "stop");
  assert.equal(resolved.banner.chip, "STOP");
  assert.equal(resolved.banner.title, "Stop today");
  assert.equal(resolved.banner.tone, "red");
  assert.equal(resolved.blocksTraining, true);
  assert.equal(resolved.canCompleteSession, false);
});

test("authoritative STOP overrides pull-back presentation as well as session safety", () => {
  const resolved = resolveTodayDecision({
    ...BASE_STATE,
    today: {
      ...BASE_STATE.today,
      recommendation_state: "pull_back",
      recommendation_reason: "Sharp work ready.\nEverything feels good.\nTrain normally.",
      decision_tier: "stop",
    },
  });

  assert.equal(resolved.authoritativeTier, "stop");
  assert.equal(resolved.displayTier, "stop");
  assert.ok(resolved.banner);
  assert.equal(resolved.banner.displayState, "stop");
  assert.equal(resolved.banner.chip, "STOP");
  assert.notEqual(resolved.banner.chip, "PULL BACK");
  assert.equal(resolved.banner.title, "Stop today");
  assert.equal(resolved.banner.detail, "A safety restriction is blocking training today.");
  assert.equal(
    resolved.banner.action,
    "Do not start today's planned session. Follow the injury and safety guidance below.",
  );
  assert.equal(resolved.banner.tone, "red");
  assert.equal(getTierMeta(resolved.displayTier).label, "Stop today");
  assert.equal(resolved.blocksTraining, true);
  assert.equal(resolved.canCompleteSession, false);
  assert.equal(resolved.useSafeReplacement, true);
});

test("future previews remain non-completable and never get today's replacement", () => {
  const resolved = resolveTodayDecision({
    ...BASE_STATE,
    today: {
      ...BASE_STATE.today,
      recommendation_state: "pull_back",
      decision_tier: "stop",
      next_session: {
        ...BASE_STATE.today.next_session,
        session_relation: "next",
      },
      session_scope: "next",
    },
  });

  assert.equal(resolved.displayTier, "preview");
  assert.equal(resolved.sessionIsToday, false);
  assert.equal(resolved.canCompleteSession, false);
  assert.equal(resolved.useSafeReplacement, false);
  assert.equal(resolved.tone, "neutral");
});

test("the banner adapter stays presentation-only", () => {
  const banner = getTodayDecisionBanner("pull_back", "Train normally.");
  assert.ok(banner);
  assert.equal("blocksTraining" in banner, false);
});

test("frontend does not create a separate severe-injury override", () => {
  const state: TodayCommandView = {
    ...BASE_STATE,
    open_injuries: [
      {
        id: "injury-1",
        athlete_id: "athlete-1",
        source: "today",
        body_area: "knee",
        description: "left knee",
        severity: "severe",
        status: "open",
        created_at: "2026-06-18T10:00:00Z",
        updated_at: "2026-06-18T10:00:00Z",
      },
    ],
  };

  assert.equal(getInjuryOverrideBanner(state, "Boxing conditioning"), null);
});
