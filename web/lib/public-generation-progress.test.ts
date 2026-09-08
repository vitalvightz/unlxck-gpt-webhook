import assert from "node:assert/strict";
import test from "node:test";

import { getPublicMilestoneIndex, getPublicProgress } from "./public-generation-progress.ts";

const milestone = (code: string) => ({ code, label: "safe", detail: "", at: "2026-01-01T00:00:00Z" });

test("uses only persisted public milestone codes as anchors", () => {
  assert.equal(getPublicMilestoneIndex("running", [milestone("profile_ready"), milestone("building_sessions")]), 2);
  assert.equal(getPublicMilestoneIndex("running", [milestone("stage2_model_call_started")]), 0);
});

test("progress is monotonic across later polls and reconnect time", () => {
  const started = 1_000;
  const early = getPublicProgress("running", [milestone("designing_camp")], started, 20_000);
  const later = getPublicProgress("running", [milestone("designing_camp")], started, 80_000);
  const reconnected = getPublicProgress("running", [milestone("building_sessions")], started, 80_000);
  assert.ok(later >= early);
  assert.ok(reconnected >= later);
});

test("live progress holds below completion and completion alone reaches 100", () => {
  assert.ok(getPublicProgress("running", [milestone("final_checks")], 1, 99_999_999) < 100);
  assert.ok(getPublicProgress("finalizing", [milestone("camp_ready")], 1, 2) < 100);
  assert.equal(getPublicProgress("finalizing", [milestone("camp_ready")], 1, 2, 94, true), 100);
});

test("reconnect floor prevents a truncated milestone history from regressing", () => {
  const restored = getPublicProgress("running", [milestone("profile_ready")], 1_000, 2_000, 72);
  assert.equal(restored, 72);
});

test("a retry starts independently from the failed job floor", () => {
  const failedJobFloor = getPublicProgress("failed", [milestone("final_checks")], 1_000, 2_000, 91);
  const retry = getPublicProgress("running", [milestone("profile_ready")], 2_000, 2_000);
  assert.equal(failedJobFloor, 91);
  assert.equal(retry, 18);
});

test("a stalled final-check build holds below 100", () => {
  const stalled = getPublicProgress("running", [milestone("final_checks")], 1, 60 * 60_000, 93);
  assert.ok(stalled >= 93);
  assert.ok(stalled < 100);
});
