import test from "node:test";
import assert from "node:assert/strict";

import {
  checkinFlagLabels,
  checkinSummary,
  injurySeverityTone,
  injuryStatusLabel,
  injuryStatusTone,
  recommendationLabel,
  recommendationTone,
  sessionStatusLabel,
  sessionStatusTone,
} from "./history.ts";
import type { TodayCheckinHistoryRecord } from "@/lib/types";

test("session status tones follow the green/amber/red contract", () => {
  assert.equal(sessionStatusTone("done"), "green");
  assert.equal(sessionStatusTone("modified"), "amber");
  assert.equal(sessionStatusTone("skipped"), "red");
  assert.equal(sessionStatusTone("started"), "neutral");
  assert.equal(sessionStatusTone("not_started"), "neutral");
});

test("session status labels are short row labels", () => {
  assert.equal(sessionStatusLabel("done"), "Done");
  assert.equal(sessionStatusLabel("modified"), "Modified");
  assert.equal(sessionStatusLabel("skipped"), "Skipped");
});

test("recommendation tones map train/modify/pull-back to green/amber/red", () => {
  assert.equal(recommendationTone("train_as_planned"), "green");
  assert.equal(recommendationTone("modify"), "amber");
  assert.equal(recommendationTone("pull_back"), "red");
  assert.equal(recommendationTone("not_checked_in"), "neutral");
  assert.equal(recommendationLabel("pull_back"), "Pull back");
});

test("injury severity and status tones", () => {
  assert.equal(injurySeverityTone("mild"), "neutral");
  assert.equal(injurySeverityTone("moderate"), "amber");
  assert.equal(injurySeverityTone("severe"), "red");
  assert.equal(injuryStatusTone("open"), "red");
  assert.equal(injuryStatusTone("monitoring"), "amber");
  assert.equal(injuryStatusTone("resolved"), "green");
  assert.equal(injuryStatusLabel("monitoring"), "Monitoring");
});

function checkin(overrides: Partial<TodayCheckinHistoryRecord> = {}): TodayCheckinHistoryRecord {
  return {
    id: "c1",
    athlete_id: "a1",
    plan_id: "p1",
    training_day: "2026-07-01",
    sleep: "good",
    body: "normal",
    pain: "none",
    phase: "GPP",
    recommendation_state: "train_as_planned",
    ...overrides,
  };
}

test("checkinFlagLabels lists only ticked safety flags", () => {
  assert.deepEqual(checkinFlagLabels(checkin()), []);
  assert.deepEqual(
    checkinFlagLabels(checkin({ sharp_pain: true, swelling: true })),
    ["Sharp pain", "Swelling"],
  );
});

test("checkinSummary is a compact sleep/body/pain line", () => {
  assert.equal(checkinSummary(checkin({ sleep: "poor" })), "Sleep poor · Body normal · Pain none");
});
