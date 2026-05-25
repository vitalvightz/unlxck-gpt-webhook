import test from "node:test";
import assert from "node:assert/strict";

import { getGenerationStatusTarget, latestFailedJobHasOpenablePlan, shouldRenderPassiveLatestJobRibbon } from "./global-generation-status";

test("active generation states route to generate workspace", () => {
  assert.equal(getGenerationStatusTarget("queued", null, null, "self_serve", null), "/generate");
  assert.equal(getGenerationStatusTarget("running", null, null, "self_serve", null), "/generate");
  assert.equal(getGenerationStatusTarget("finalizing", null, null, "self_serve", null), "/generate");
});

test("completed generation with plan id routes to plan detail", () => {
  assert.equal(getGenerationStatusTarget("completed", "plan_123", "completed", "admin_latest_intake", "ath_1"), "/plans/plan_123");
});

test("review-required generation routes with review query flag", () => {
  assert.equal(
    getGenerationStatusTarget("completed", "plan_123", "review_required", "admin_latest_intake", "ath_1"),
    "/plans/plan_123?review_required=1",
  );
});

test("failed generation has no link target", () => {
  assert.equal(getGenerationStatusTarget("failed", "plan_123", null, "admin_latest_intake", "ath_1"), null);
});

test("failed latest job with plan shows open-plan path", () => {
  assert.equal(
    latestFailedJobHasOpenablePlan({ status: "failed", plan_id: "plan_123", latest_plan_id: null }),
    true,
  );
});


test("terminal states without plan id have no link target", () => {
  assert.equal(getGenerationStatusTarget("completed", null, "completed", "admin_latest_intake", "ath_1"), null);
  assert.equal(getGenerationStatusTarget("completed", null, "review_required", "admin_latest_intake", "ath_1"), null);
});


test("running quick_build and self_serve stay on generate", () => {
  assert.equal(getGenerationStatusTarget("running", null, null, "self_serve", "ath_1"), "/generate");
  assert.equal(getGenerationStatusTarget("running", null, null, "quick_build", "ath_1"), "/generate");
});

test("running admin_latest_intake routes to admin athlete profile", () => {
  assert.equal(getGenerationStatusTarget("running", null, null, "admin_latest_intake", "ath_123"), "/admin/athletes/ath_123");
});

test("running admin_triage_resume routes to plan when linked, else athlete profile", () => {
  assert.equal(getGenerationStatusTarget("running", "plan_999", null, "admin_triage_resume", "ath_123"), "/plans/plan_999");
  assert.equal(getGenerationStatusTarget("running", null, null, "admin_triage_resume", "ath_123"), "/admin/athletes/ath_123");
});

test("completed admin generation routes to job-linked plan", () => {
  assert.equal(getGenerationStatusTarget("completed", "plan_abc", "completed", "admin_latest_intake", "ath_123"), "/plans/plan_abc");
});

test("admin generation running target never points to onboarding", () => {
  const target = getGenerationStatusTarget("running", null, null, "admin_latest_intake", "ath_123");
  assert.notEqual(target, "/onboarding");
});

test("no active generation plus latest completed job with plan id is hidden", () => {
  assert.equal(shouldRenderPassiveLatestJobRibbon({ status: "completed", plan_id: "plan_123" }), false);
});

test("no active generation plus latest failed job remains visible", () => {
  assert.equal(shouldRenderPassiveLatestJobRibbon({ status: "failed", plan_id: null }), true);
});

test("no active generation plus latest review_required job with plan id is visible", () => {
  assert.equal(shouldRenderPassiveLatestJobRibbon({ status: "review_required", plan_id: "plan_123" }), true);
});

test("active running job path still routes to generate", () => {
  assert.equal(getGenerationStatusTarget("running", null, null, "self_serve", null), "/generate");
});

test("generic ribbon guard blocks render when phase/status/target are all null and passive job is not actionable", () => {
  assert.equal(shouldRenderPassiveLatestJobRibbon({ status: "completed", plan_id: "plan_555" }), false);
});
