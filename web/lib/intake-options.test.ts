import assert from "node:assert/strict";
import test from "node:test";

import { canonicalizeEquipmentAccessValues, cycleGuidedInjurySeverity, normalizeGuidedInjurySeverity } from "./intake-options.ts";

test("cycleGuidedInjurySeverity advances low → moderate → high → low", () => {
  assert.equal(cycleGuidedInjurySeverity("low"), "moderate");
  assert.equal(cycleGuidedInjurySeverity("moderate"), "high");
  assert.equal(cycleGuidedInjurySeverity("high"), "low");
});

test("catalogue aliases never migrate persisted athlete equipment selections", () => {
  const saved = ["kettlebells", "weighted_vest", "rowing_machine", "double-end_bag", "mat", "mats", "mini_band", "thai_pads", "partner"];
  assert.deepEqual(canonicalizeEquipmentAccessValues(JSON.parse(JSON.stringify(saved))),
    [...saved.slice(0, -2), "pads", "partner"]);
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
