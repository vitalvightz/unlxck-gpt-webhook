import test from "node:test";
import assert from "node:assert/strict";

import { getRecoveryProfileLabel, RECOVERY_PROFILE_OPTIONS } from "@/lib/intake-options";

test("recovery profile labels preserve the existing planner values", () => {
  assert.deepEqual(RECOVERY_PROFILE_OPTIONS, [
    { value: "low", label: "Faster" },
    { value: "moderate", label: "Average" },
    { value: "high", label: "Slower" },
  ]);
});

test("saved recovery values load with their new labels", () => {
  assert.equal(getRecoveryProfileLabel("low"), "Faster");
  assert.equal(getRecoveryProfileLabel("moderate"), "Average");
  assert.equal(getRecoveryProfileLabel("high"), "Slower");
});
