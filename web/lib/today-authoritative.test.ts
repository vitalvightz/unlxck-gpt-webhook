import test from "node:test";
import assert from "node:assert/strict";

import {
  getInjuryOverrideBanner,
  getTodayDecisionBanner,
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

test("prose cannot turn a backend green decision into a training block", () => {
  const banner = getTodayDecisionBanner(
    "train_as_planned",
    "No training today.\nRed flag detected. Seek medical advice.",
  );

  assert.ok(banner);
  assert.equal(banner.displayState, "go");
  assert.equal(banner.chip, "GO");
  assert.equal(banner.tone, "green");
  assert.equal(banner.blocksTraining, false);
});

test("prose cannot weaken a backend pull-back decision", () => {
  const banner = getTodayDecisionBanner(
    "pull_back",
    "Sharp work ready.\nEverything feels good.\nTrain normally.",
  );

  assert.ok(banner);
  assert.equal(banner.displayState, "pull_back");
  assert.equal(banner.chip, "PULL BACK");
  assert.equal(banner.tone, "red");
  assert.equal(banner.blocksTraining, true);
});

test("preview scope is display-only and never training-cleared", () => {
  const banner = getTodayDecisionBanner("train_as_planned", "Train as planned.", {
    isPreview: true,
  });

  assert.ok(banner);
  assert.equal(banner.displayState, "preview");
  assert.equal(banner.chip, "PREVIEW");
  assert.equal(banner.tone, "neutral");
  assert.equal(banner.blocksTraining, false);
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
