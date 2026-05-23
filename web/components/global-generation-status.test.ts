import test from "node:test";
import assert from "node:assert/strict";

import { getGenerationStatusTarget } from "./global-generation-status";

test("active generation states route to generate workspace", () => {
  assert.equal(getGenerationStatusTarget("queued", null, null), "/generate");
  assert.equal(getGenerationStatusTarget("running", null, null), "/generate");
  assert.equal(getGenerationStatusTarget("finalizing", null, null), "/generate");
});

test("completed generation with plan id routes to plan detail", () => {
  assert.equal(getGenerationStatusTarget("completed", "plan_123", "completed"), "/plans/plan_123");
});

test("review-required generation routes with review query flag", () => {
  assert.equal(
    getGenerationStatusTarget("completed", "plan_123", "review_required"),
    "/plans/plan_123?review_required=1",
  );
});

test("failed generation has no link target", () => {
  assert.equal(getGenerationStatusTarget("failed", "plan_123", null), null);
});


test("terminal states without plan id have no link target", () => {
  assert.equal(getGenerationStatusTarget("completed", null, "completed"), null);
  assert.equal(getGenerationStatusTarget("completed", null, "review_required"), null);
});
