import test from "node:test";
import assert from "node:assert/strict";

import {
  formatElapsed,
  formatGenerationElapsedLabel,
  isGenerationElapsedFrozen,
  resolveGenerationElapsedMs,
} from "./generation-elapsed";

const START = Date.parse("2026-07-31T10:00:00Z");

test("a live job's elapsed time is measured against now", () => {
  assert.equal(
    formatGenerationElapsedLabel({
      startedAtMs: START,
      endedAtMs: null,
      nowMs: START + 292_000,
    }),
    "4m 52s",
  );
});

test("a terminal job's elapsed time is measured against the backend end timestamp", () => {
  // The bottom ribbon kept climbing past the moment the job actually stopped
  // because it only ever subtracted from Date.now().
  const endedAtMs = START + 279_000;
  assert.equal(
    formatGenerationElapsedLabel({ startedAtMs: START, endedAtMs, nowMs: START + 292_000 }),
    "4m 39s",
  );
  // ...and stays there no matter how much later the component re-renders.
  assert.equal(
    formatGenerationElapsedLabel({ startedAtMs: START, endedAtMs, nowMs: START + 3_600_000 }),
    "4m 39s",
  );
});

test("elapsed time is null without a start timestamp", () => {
  assert.equal(resolveGenerationElapsedMs({ startedAtMs: null, nowMs: START }), null);
  assert.equal(formatGenerationElapsedLabel({ startedAtMs: null, nowMs: START }), null);
});

test("clock skew that puts the end before the start never renders a negative duration", () => {
  assert.equal(
    formatGenerationElapsedLabel({ startedAtMs: START, endedAtMs: START - 4_000, nowMs: START }),
    "0s",
  );
});

test("elapsed formatting pads seconds only once minutes are shown", () => {
  assert.equal(formatElapsed(6_000), "6s");
  assert.equal(formatElapsed(66_000), "1m 06s");
  assert.equal(formatElapsed(226_000), "3m 46s");
});

test("the frozen check is what the UI branches on to stop ticking", () => {
  assert.equal(isGenerationElapsedFrozen(null), false);
  assert.equal(isGenerationElapsedFrozen(undefined), false);
  assert.equal(isGenerationElapsedFrozen(START), true);
  // 0 is a real epoch value, not an absence.
  assert.equal(isGenerationElapsedFrozen(0), true);
});
