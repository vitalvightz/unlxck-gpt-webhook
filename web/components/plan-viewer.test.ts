import test from "node:test";
import assert from "node:assert/strict";

import { buildReviewSummary, hasBlockedTriageStubText } from "./plan-viewer";

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
