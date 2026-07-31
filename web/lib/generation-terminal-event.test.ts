import test from "node:test";
import assert from "node:assert/strict";

import {
  isTerminalGenerationStatus,
  resolveGenerationEndedAtMs,
} from "./generation-terminal-event";

test("terminal statuses include the legacy aliases the backend still emits", () => {
  assert.equal(isTerminalGenerationStatus("completed"), true);
  assert.equal(isTerminalGenerationStatus("review_required"), true);
  assert.equal(isTerminalGenerationStatus("failed"), true);
  assert.equal(isTerminalGenerationStatus("held_for_review"), true);
  assert.equal(isTerminalGenerationStatus("publishable_with_flags"), true);
});

test("live statuses are not terminal", () => {
  assert.equal(isTerminalGenerationStatus("queued"), false);
  assert.equal(isTerminalGenerationStatus("running"), false);
  assert.equal(isTerminalGenerationStatus(null), false);
  assert.equal(isTerminalGenerationStatus(undefined), false);
});

test("the end timestamp prefers completed_at", () => {
  assert.equal(
    resolveGenerationEndedAtMs({
      completed_at: "2026-07-31T10:04:39Z",
      updated_at: "2026-07-31T10:05:10Z",
    }),
    Date.parse("2026-07-31T10:04:39Z"),
  );
});

test("the end timestamp falls back to updated_at when the job has no completed_at", () => {
  assert.equal(
    resolveGenerationEndedAtMs({ completed_at: null, updated_at: "2026-07-31T10:04:39Z" }),
    Date.parse("2026-07-31T10:04:39Z"),
  );
});

test("a job with no usable timestamp still freezes on the caller's fallback", () => {
  // Returning null here would leave the timer running against Date.now()
  // forever, which is the exact bug this module exists to close.
  const fallback = Date.parse("2026-07-31T10:06:00Z");
  assert.equal(resolveGenerationEndedAtMs({ completed_at: null, updated_at: "" }, fallback), fallback);
  assert.equal(resolveGenerationEndedAtMs(null, fallback), fallback);
  assert.equal(resolveGenerationEndedAtMs({ completed_at: null, updated_at: null }), null);
});
