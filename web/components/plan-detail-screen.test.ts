import test from "node:test";
import assert from "node:assert/strict";

import { ApiError } from "@/lib/api";
import { shouldRetryPlanLoad } from "./plan-detail-screen";

test("retries a 404 — the read-after-write window for a freshly completed plan", () => {
  assert.equal(shouldRetryPlanLoad(new ApiError("plan not found", 404)), true);
});

test("does not retry a 403 — the plan is genuinely not the viewer's", () => {
  assert.equal(shouldRetryPlanLoad(new ApiError("not allowed", 403)), false);
});

test("does not retry exhausted gateway failures", () => {
  assert.equal(shouldRetryPlanLoad(new ApiError("gateway", 502)), false);
});

test("does not retry non-API errors", () => {
  assert.equal(shouldRetryPlanLoad(new Error("boom")), false);
  assert.equal(shouldRetryPlanLoad(null), false);
});
