import test from "node:test";
import assert from "node:assert/strict";

import {
  buildPlanTextCards,
  buildReviewSummary,
  canRetryResumeGenerationForPlan,
  getAdminReviewHeading,
  hasBlockedTriageStubText,
  isPlanReleasedToAthlete,
  isProtectedTriageResumePendingState,
  readInjuryTriage,
  readRawTriageMode,
  resolveApprovalAfterError,
  shouldShowProtectedResumeAdminReview,
} from "./plan-viewer";
import { ApiError, RETRYABLE_NETWORK_MESSAGE } from "@/lib/api";
import { HARD_STAGE2_BLOCKER_CODES } from "@/lib/stage2-policy";
import type { PlanDetail } from "@/lib/types";

function makePlan(overrides: { status?: string; planText?: string }): PlanDetail {
  return {
    status: overrides.status ?? "ready",
    outputs: { plan_text: overrides.planText ?? "# Plan body" },
  } as unknown as PlanDetail;
}

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

test("legacy soft blocking warnings do not block release summary", () => {
  const summary = buildReviewSummary(
    {
      warnings: [{ code: "missing_required_element", message: "Missing phase element." }],
      blocking_warnings: [{ code: "missing_required_element", message: "Missing phase element." }],
      is_publishable: false,
    },
    "stage2_pass",
    { hasBlockedTriageStubText: false },
  );

  assert.equal(summary.isPublishable, true);
  assert.equal(summary.blockingCount, 0);
  assert.equal(summary.hasIssues, false);
});

test("hard blocking warnings still hold release summary", () => {
  const hardBlockerCode = HARD_STAGE2_BLOCKER_CODES[0];
  const summary = buildReviewSummary(
    {
      blocking_warnings: [
        {
          code: hardBlockerCode,
          message: "Hard blocker present.",
        },
      ],
    },
    "stage2_failed",
    { hasBlockedTriageStubText: false },
  );

  assert.equal(summary.isPublishable, false);
  assert.equal(summary.blockingCount, 1);
  assert.equal(summary.hasIssues, true);
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

test("isPlanReleasedToAthlete requires an athlete-visible status with plan text", () => {
  assert.equal(isPlanReleasedToAthlete(makePlan({ status: "ready", planText: "# Plan" })), true);
  assert.equal(
    isPlanReleasedToAthlete(makePlan({ status: "publishable_with_flags", planText: "x" })),
    true,
  );
  // Ready but empty plan text is not yet releasable.
  assert.equal(isPlanReleasedToAthlete(makePlan({ status: "ready", planText: "   " })), false);
  // Non-athlete-visible status is never released, even with plan text.
  assert.equal(
    isPlanReleasedToAthlete(makePlan({ status: "review_required", planText: "# Plan" })),
    false,
  );
});

test("resolveApprovalAfterError treats a retryable timeout as approved when getPlan reads ready", async () => {
  const readyPlan = makePlan({ status: "ready", planText: "# Released" });
  let calls = 0;
  const recovered = await resolveApprovalAfterError({
    error: new Error(RETRYABLE_NETWORK_MESSAGE),
    fetchPlan: async () => {
      calls += 1;
      return readyPlan;
    },
    wait: async () => {},
  });

  assert.equal(recovered, readyPlan);
  assert.equal(calls, 1);
});

test("resolveApprovalAfterError ignores non-retryable errors without refetching", async () => {
  let calls = 0;
  const recovered = await resolveApprovalAfterError({
    error: new ApiError("bad request", 400),
    fetchPlan: async () => {
      calls += 1;
      return makePlan({ status: "ready", planText: "# Released" });
    },
    wait: async () => {},
  });

  assert.equal(recovered, null);
  assert.equal(calls, 0);
});

test("resolveApprovalAfterError gives up after exhausting attempts when never released", async () => {
  let calls = 0;
  const recovered = await resolveApprovalAfterError({
    error: new Error(RETRYABLE_NETWORK_MESSAGE),
    attempts: 3,
    fetchPlan: async () => {
      calls += 1;
      return makePlan({ status: "review_required", planText: "" });
    },
    wait: async () => {},
  });

  assert.equal(recovered, null);
  assert.equal(calls, 3);
});

test("resolveApprovalAfterError retries past a transient getPlan failure", async () => {
  const readyPlan = makePlan({ status: "ready", planText: "# Released" });
  let calls = 0;
  const recovered = await resolveApprovalAfterError({
    error: new Error(RETRYABLE_NETWORK_MESSAGE),
    attempts: 3,
    fetchPlan: async () => {
      calls += 1;
      if (calls === 1) {
        throw new Error("temporary fetch failure");
      }
      return readyPlan;
    },
    wait: async () => {},
  });

  assert.equal(recovered, readyPlan);
  assert.equal(calls, 2);
});

test("admin review anchor id format remains stable", () => {
  const planId = "plan_123";
  const anchorId = `admin-review-${planId}`;
  assert.equal(anchorId, "admin-review-plan_123");
});

test("legacy plan text is split into renderable cards instead of one raw block", () => {
  const cards = buildPlanTextCards(
    [
      "Lead notes",
      "- Injury: keep cut covered.",
      "",
      "## GPP — Week 1",
      "Why: build the base.",
      "- Assault Bike: 25 min Zone 2.",
      "- Rehab: Neutral-grip holds.",
      "",
      "## Final notes",
      "Stop on dizziness.",
    ].join("\n"),
  );

  assert.deepEqual(cards, [
    {
      title: "Lead notes",
      lines: ["Injury: keep cut covered."],
    },
    {
      title: "GPP — Week 1",
      lines: ["Why: build the base.", "Assault Bike: 25 min Zone 2.", "Rehab: Neutral-grip holds."],
    },
    {
      title: "Final notes",
      lines: ["Stop on dizziness."],
    },
  ]);
});

test("recent generated plan headings become separate cards", () => {
  const cards = buildPlanTextCards(
    "Lead notes - Injury: cover the cut. GPP — Week 1 (D-33 to D-27) — Build aerobic base D-32 (Wednesday) — Aerobic support Why: restore repeatability. - Easy Assault Bike: 25 min. Final notes - Stop on dizziness.",
  );

  assert.deepEqual(
    cards.map((card) => card.title),
    ["Lead notes", "GPP — Week 1 (D-33 to D-27) — Build aerobic base", "D-32 (Wednesday) — Aerobic support", "Final notes"],
  );
});
