import test from "node:test";
import assert from "node:assert/strict";

import {
  buildReviewSummary,
  hasBlockedTriageStubText,
  isProtectedTriageResumePendingState,
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

test("empty athlete text plus final blocked stub is protected", () => {
  const protectedState = isProtectedTriageResumePendingState({
    isTriageBlocked: false,
    stage2Status: "stage2_pass",
    containsBlockedTriageStub: false,
    athletePlanText: "",
    finalPlanText:
      "## Injury Triage: Restricted Rehab Only\nNormal fight-camp planning is intentionally suspended\nClinician clearance is required",
  });

  assert.equal(protectedState, true);
});
