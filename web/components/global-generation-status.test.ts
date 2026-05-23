import test from "node:test";
import assert from "node:assert/strict";

import { getGenerationStatusTarget } from "./global-generation-status";

test("routes in-progress generation status to /generate", () => {
  assert.equal(getGenerationStatusTarget("generating", null), "/generate");
  assert.equal(getGenerationStatusTarget("submitting", null), "/generate");
  assert.equal(getGenerationStatusTarget(null, null), "/generate");
});

test("routes completed generation with plan id to plan detail", () => {
  assert.equal(getGenerationStatusTarget("completed", "plan_123"), "/plans/plan_123");
});

test("routes completed generation without plan id to /generate", () => {
  assert.equal(getGenerationStatusTarget("completed", null), "/generate");
});

test("failed generation has no link target", () => {
  assert.equal(getGenerationStatusTarget("failed", "plan_123"), null);
  assert.equal(getGenerationStatusTarget("failed", null), null);
});
