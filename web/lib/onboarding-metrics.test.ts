import test from "node:test";
import assert from "node:assert/strict";

import { describeFirstPlanConversion, formatWaitDuration } from "@/lib/onboarding-metrics";

test("wait durations read compactly at every scale", () => {
  assert.equal(formatWaitDuration(null), "-");
  assert.equal(formatWaitDuration(42), "42s");
  assert.equal(formatWaitDuration(240), "4m");
  assert.equal(formatWaitDuration(3600), "1h");
  assert.equal(formatWaitDuration(80 * 60), "1h 20m");
  assert.equal(formatWaitDuration(2 * 86400 + 3 * 3600), "2d 3h");
});

test("conversion line names activated signups and the p75", () => {
  assert.equal(
    describeFirstPlanConversion({ window_days: 30, signups: 5, with_usable_plan: 4, median_seconds: 240, p75_seconds: 360 }),
    "4 of 5 signups have a plan (30d). p75 6m.",
  );
  assert.equal(
    describeFirstPlanConversion({ window_days: 30, signups: 0, with_usable_plan: 0, median_seconds: null, p75_seconds: null }),
    "No signups in the last 30 days.",
  );
});
