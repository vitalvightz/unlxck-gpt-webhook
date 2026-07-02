import test from "node:test";
import assert from "node:assert/strict";

import {
  getGenerationStatusTarget,
  isGenerationRibbonTargetRedundant,
  isProtectedTriageLatestJob,
  latestCompletedJobOpenablePlanId,
  latestFailedJobHasOpenablePlan,
  shouldRenderPassiveLatestJobRibbon,
} from "./global-generation-status";

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

test("generation ribbon target is redundant when path matches target without query", () => {
  assert.equal(isGenerationRibbonTargetRedundant("/plans/plan_123", "/plans/plan_123"), true);
  assert.equal(isGenerationRibbonTargetRedundant("/plans/plan_123", "/plans/plan_123?review_required=1"), true);
});

test("generation ribbon target is redundant on the plan dashboard for plan detail links", () => {
  assert.equal(isGenerationRibbonTargetRedundant("/plans", "/plans/plan_123"), true);
});

test("generation ribbon target is not redundant when route is unrelated", () => {
  assert.equal(isGenerationRibbonTargetRedundant("/plans/plan_123", "/plans/plan_456"), false);
  assert.equal(isGenerationRibbonTargetRedundant("/today", "/plans/plan_123"), false);
  assert.equal(isGenerationRibbonTargetRedundant(null, "/plans/plan_123"), false);
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

test("completed latest job with only latest_plan_id is openable via latest_plan_id", () => {
  assert.equal(
    latestCompletedJobOpenablePlanId({ status: "completed", plan_id: null, latest_plan_id: "plan_latest" }),
    "plan_latest",
  );
});

test("completed latest job that already has plan_id is not opened via latest_plan_id", () => {
  assert.equal(
    latestCompletedJobOpenablePlanId({ status: "completed", plan_id: "plan_main", latest_plan_id: "plan_latest" }),
    null,
  );
});

test("failed latest job with latest_plan_id is not treated as a completed openable plan", () => {
  assert.equal(
    latestCompletedJobOpenablePlanId({ status: "failed", plan_id: null, latest_plan_id: "plan_latest" }),
    null,
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

test("isProtectedTriageLatestJob detects requires_admin_resume", () => {
  assert.equal(isProtectedTriageLatestJob({ requires_admin_resume: true }), true);
});

test("isProtectedTriageLatestJob detects triage_blocked stage2_status", () => {
  assert.equal(isProtectedTriageLatestJob({ stage2_status: "triage_blocked" }), true);
});

test("isProtectedTriageLatestJob returns false for normal completed jobs", () => {
  assert.equal(isProtectedTriageLatestJob({ stage2_status: "stage2_pass" }), false);
  assert.equal(isProtectedTriageLatestJob({}), false);
  assert.equal(isProtectedTriageLatestJob(null), false);
});

test("triage-blocked completed job with plan_id still surfaces a passive ribbon for admin review", () => {
  assert.equal(
    shouldRenderPassiveLatestJobRibbon({
      status: "completed",
      plan_id: "plan_blocked",
      requires_admin_resume: true,
    }),
    true,
  );
});

test("triage-blocked review_required job without plan id surfaces a passive ribbon for admin review", () => {
  // New-style triage outcomes: no plan row, status is review_required,
  // requires_admin_resume signals the protected-triage hold.
  assert.equal(
    shouldRenderPassiveLatestJobRibbon({
      status: "review_required",
      plan_id: null,
      requires_admin_resume: true,
      stage2_status: "triage_blocked",
    }),
    true,
  );
});

test("review_required job without plan id and no admin-resume signal is not retained as ribbon", () => {
  // A review_required job that lost its plan id but isn't a triage hold
  // has nothing actionable for the user, so the ribbon must stay hidden.
  assert.equal(
    shouldRenderPassiveLatestJobRibbon({
      status: "review_required",
      plan_id: null,
    }),
    false,
  );
});
