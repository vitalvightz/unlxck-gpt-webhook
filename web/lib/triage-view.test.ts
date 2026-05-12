import test from "node:test";
import assert from "node:assert/strict";

import { hasTriageResumeApproval } from "./triage-view";

test("hasTriageResumeApproval returns true for triage_resume_approved stage2_status", () => {
  assert.equal(hasTriageResumeApproval({ admin_outputs: { stage2_status: "triage_resume_approved" } } as never), true);
});

test("hasTriageResumeApproval returns true for why_log clear flag", () => {
  assert.equal(
    hasTriageResumeApproval({ admin_outputs: { why_log: { triage_regeneration_cleared: true } } } as never),
    true,
  );
});

test("hasTriageResumeApproval returns false when approval markers are absent", () => {
  assert.equal(hasTriageResumeApproval({ admin_outputs: { stage2_status: "triage_blocked" } } as never), false);
});
