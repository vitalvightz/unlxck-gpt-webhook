import test from "node:test";
import assert from "node:assert/strict";

import { getGenerationStatusTarget } from "./global-generation-status";

test("active generation states have no navigation target", () => {
  assert.equal(getGenerationStatusTarget("queued", null), null);
  assert.equal(getGenerationStatusTarget("running", null), null);
  assert.equal(getGenerationStatusTarget("finalizing", null), null);
});

test("completed generation with plan id routes to plan detail", () => {
  assert.equal(getGenerationStatusTarget("completed", "plan_123"), "/plans/plan_123");
});

test("failed generation has no link target", () => {
  assert.equal(getGenerationStatusTarget("failed", "plan_123"), null);
});
