import assert from "node:assert/strict";
import test from "node:test";

import { cycleGuidedInjurySeverity, normalizeGuidedInjurySeverity } from "./intake-options.ts";

test("cycleGuidedInjurySeverity advances low → moderate → high → low", () => {
  assert.equal(cycleGuidedInjurySeverity("low"), "moderate");
  assert.equal(cycleGuidedInjurySeverity("moderate"), "high");
  assert.equal(cycleGuidedInjurySeverity("high"), "low");
});

test("cycleGuidedInjurySeverity starts an unset or unknown severity at low", () => {
  assert.equal(cycleGuidedInjurySeverity(""), "low");
  assert.equal(cycleGuidedInjurySeverity(null), "low");
  assert.equal(cycleGuidedInjurySeverity("nonsense"), "low");
});

test("cycleGuidedInjurySeverity normalizes aliases before advancing", () => {
  // "mild" → low → moderate; "severe" → high → low
  assert.equal(cycleGuidedInjurySeverity("mild"), "moderate");
  assert.equal(cycleGuidedInjurySeverity("severe"), "low");
  assert.equal(normalizeGuidedInjurySeverity("mild"), "low");
});
