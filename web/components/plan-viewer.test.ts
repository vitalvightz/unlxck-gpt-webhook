import test from "node:test";
import assert from "node:assert/strict";

import {
  buildReviewSummary,
  canRetryResumeGenerationForPlan,
  getAdminReviewHeading,
  hasBlockedTriageStubText,
  isProtectedTriageResumePendingState,
  readInjuryTriage,
  readRawTriageMode,
  shouldShowProtectedResumeAdminReview,
} from "./plan-viewer";

test("triage_resume_approved with empty validator report and restricted rehab stub is not publishable", () => {
  const hasStub = hasBlockedTriageStubText(
    "## Injury Triage: Restricted Rehab Only\nNormal fight-camp planning is intentionally suspended\nClinician clearance is required",
    "",
  );
  assert.equal(hasStub, true);

  const summary = buildReviewSummary({}, "triage_resume_approved", {
    hasBlockedTriageStubText: hasStub,
  });

  assert.equal(summary.isPublishable, false);
  assert.match(summary.headline, /Resume approved — regeneration pending/i);
});

test("ready final stage2 status without blocked stub can be publishable", () => {
  const summary = buildReviewSummary({ is_publishable: true }, "stage2_pass", {
    hasBlockedTriageStubText: false,
  });

  assert.equal(summary.isPublishable, true);
});

test("soft review warnings do not block release summary", () => {
  const summary = buildReviewSummary(
    {
      warnings: [{ code: "generic_filler_phrase", message: "Low-trust filler." }],
      review_flags: [{ code: "generic_filler_phrase", message: "Low-trust filler." }],
      review_flag_count: 1,
      is_publishable: false,
    },
    "stage2_pass",
    { hasBlockedTriageStubText: false },
  );

  assert.equal(summary.isPublishable, true);
  assert.equal(summary.hasIssues, false);
  assert.match(summary.headline, /ready to release/i);
});

test("triage resume approved state is protected even without explicit stub", () => {
  const protectedState = isProtectedTriageResumePendingState({
    isTriageBlocked: false,
    stage2Status: "triage_resume_approved",
    containsBlockedTriageStub: false,
    athletePlanText: "",
    finalPlanText: "Structured draft waiting for regeneration",
  });

  assert.equal(protectedState, true);
});

test("protected resume-approved state exposes retry action and hides release controls", () => {
  const showProtected = shouldShowProtectedResumeAdminReview({
    isTriageBlocked: false,
    isProtectedTriageResumePending: true,
    hasResumeApproval: true,
  });
  assert.equal(showProtected, true);
  assert.equal(
    getAdminReviewHeading({ showProtectedResumeAdminReview: showProtected, hasResumeApproval: true }),
    "Resume generation required",
  );
});

test("readRawTriageMode keeps original mode after resume approval", () => {
  const plan = {
    status: "triage_resume_approved",
    admin_outputs: {
      stage2_status: "triage_resume_approved",
      why_log: { injury_triage: { mode: "needs_review" } },
    },
  };

  assert.equal(readRawTriageMode(plan as never), "needs_review");
  assert.equal(readInjuryTriage(plan as never)?.mode, "needs_review");
});

test("medical_hold does not allow retry resume", () => {
  const canRetry = canRetryResumeGenerationForPlan({
    isAdmin: true,
    isProtectedTriageResumePending: true,
    injuryTriageMode: "medical_hold",
  });
  assert.equal(canRetry, false);
});

test("medical_hold always blocks retry even when another source looks resumable", () => {
  const canRetry = canRetryResumeGenerationForPlan({
    isAdmin: true,
    isProtectedTriageResumePending: true,
    injuryTriageMode: "needs_review",
    rawTriageMode: "Medical_Hold",
    planStatus: "triage_resume_approved",
  });
  assert.equal(canRetry, false);
});

test("needs_review and restricted_rehab_only allow retry resume", () => {
  assert.equal(
    canRetryResumeGenerationForPlan({
      isAdmin: true,
      isProtectedTriageResumePending: true,
      injuryTriageMode: "needs_review",
    }),
    true,
  );
  assert.equal(
    canRetryResumeGenerationForPlan({
      isAdmin: true,
      isProtectedTriageResumePending: true,
      rawTriageMode: "restricted_rehab_only",
    }),
    true,
  );
});

test("admin review anchor id format remains stable", () => {
  const planId = "plan_123";
  const anchorId = `admin-review-${planId}`;
  assert.equal(anchorId, "admin-review-plan_123");
});
