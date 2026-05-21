import test from "node:test";
import assert from "node:assert/strict";

import { hasTriageResumeApproval, shouldShowTriageBlockedState } from "./triage-view";

test("hasTriageResumeApproval returns true for triage_resume_approved stage2_status", () => {
  assert.equal(hasTriageResumeApproval({ admin_outputs: { stage2_status: "triage_resume_approved" } } as never), true);
});

test("hasTriageResumeApproval returns true for why_log clear flag", () => {
  assert.equal(
    hasTriageResumeApproval({ admin_outputs: { why_log: { triage_regeneration_cleared: true } } } as never),
    true,
  );
});

test("hasTriageResumeApproval returns true for explicit triage resume override marker", () => {
  assert.equal(
    hasTriageResumeApproval({
      admin_outputs: {
        stage2_status: "generated",
        why_log: {
          injury_triage_resume_override: {
            bypassed_blocking: true,
            triage_mode: "needs_review",
          },
        },
      },
    } as any),
    true,
  );
});

test("hasTriageResumeApproval returns true when original triage summary carries triage_resume_approved", () => {
  assert.equal(
    hasTriageResumeApproval({
      admin_outputs: {
        stage2_status: "generated",
        why_log: {
          injury_triage_original: {
            mode: "needs_review",
            triage_resume_approved: true,
          },
        },
      },
    } as never),
    true,
  );
});

test("hasTriageResumeApproval returns false when approval markers are absent", () => {
  assert.equal(hasTriageResumeApproval({ admin_outputs: { stage2_status: "triage_blocked" } } as never), false);
});

test("shouldShowTriageBlockedState returns true for restricted rehab without resume approval", () => {
  assert.equal(
    shouldShowTriageBlockedState(
      { status: "ready", admin_outputs: { stage2_status: "triage_blocked" } } as never,
      "restricted_rehab_only",
    ),
    true,
  );
});

test("shouldShowTriageBlockedState returns false when triage resume is approved", () => {
  assert.equal(
    shouldShowTriageBlockedState(
      { status: "triage_blocked", admin_outputs: { stage2_status: "triage_resume_approved" } } as never,
      "restricted_rehab_only",
    ),
    false,
  );
});
