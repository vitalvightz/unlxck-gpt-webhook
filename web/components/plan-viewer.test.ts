import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  parsePlanText,
  splitLabeledSegments,
  buildReviewSummary,
  canRetryResumeGenerationForPlan,
  getAdminReviewHeading,
  hasBlockedTriageStubText,
  isPlanReleasedToAthlete,
  isProtectedTriageResumePendingState,
  isRecentlyCreatedPlan,
  readInjuryTriage,
  readRawTriageMode,
  resolveApprovalAfterError,
  shouldHoldPlanTextFallbackForStructuredPlan,
  shouldShowProtectedResumeAdminReview,
} from "./plan-viewer";
import { ApiError, RETRYABLE_NETWORK_MESSAGE } from "@/lib/api";
import { HARD_STAGE2_BLOCKER_CODES } from "@/lib/stage2-policy";
import type { PlanDetail } from "@/lib/types";

const PLAN_VIEWER_SOURCE = readFileSync(new URL("./plan-viewer.tsx", import.meta.url), "utf8");

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

test("sparring advisory omits generated why rationale", () => {
  assert.equal(PLAN_VIEWER_SOURCE.includes("Why this flag"), false);
  assert.equal(PLAN_VIEWER_SOURCE.includes("sparring-advisory-why-toggle"), false);
  assert.equal(PLAN_VIEWER_SOURCE.includes("sparring-advisory-reason"), false);
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

test("recent published plan without structured card holds the text fallback", () => {
  assert.equal(
    shouldHoldPlanTextFallbackForStructuredPlan({
      hasPublishedPlan: true,
      hasStructuredPlan: false,
      fallbackUnlocked: false,
      hasAccessToken: true,
      isRecentPlan: true,
    }),
    true,
  );
});

test("structured card or timeout unlocks the published plan view", () => {
  assert.equal(
    shouldHoldPlanTextFallbackForStructuredPlan({
      hasPublishedPlan: true,
      hasStructuredPlan: true,
      fallbackUnlocked: false,
      hasAccessToken: true,
      isRecentPlan: true,
    }),
    false,
  );
  assert.equal(
    shouldHoldPlanTextFallbackForStructuredPlan({
      hasPublishedPlan: true,
      hasStructuredPlan: false,
      fallbackUnlocked: true,
      hasAccessToken: true,
      isRecentPlan: true,
    }),
    false,
  );
});

test("triage blocked plans do not enter the structured-card hold", () => {
  assert.equal(
    shouldHoldPlanTextFallbackForStructuredPlan({
      hasPublishedPlan: true,
      hasStructuredPlan: false,
      fallbackUnlocked: false,
      hasAccessToken: true,
      isRecentPlan: true,
      isTriageBlocked: true,
    }),
    false,
  );
});

test("legacy plans without a structured card do not enter the hold", () => {
  assert.equal(
    shouldHoldPlanTextFallbackForStructuredPlan({
      hasPublishedPlan: true,
      hasStructuredPlan: false,
      fallbackUnlocked: false,
      hasAccessToken: true,
      isRecentPlan: false,
    }),
    false,
  );
});

test("plans without an access token cannot be held for structuring", () => {
  assert.equal(
    shouldHoldPlanTextFallbackForStructuredPlan({
      hasPublishedPlan: true,
      hasStructuredPlan: false,
      fallbackUnlocked: false,
      hasAccessToken: false,
      isRecentPlan: true,
    }),
    false,
  );
});

test("isRecentlyCreatedPlan honours the recent-plan threshold", () => {
  const now = Date.parse("2026-06-22T12:00:00.000Z");
  assert.equal(
    isRecentlyCreatedPlan({ created_at: "2026-06-22T11:58:00.000Z" }, now),
    true,
  );
  assert.equal(
    isRecentlyCreatedPlan({ created_at: "2026-06-22T11:50:00.000Z" }, now),
    false,
  );
  assert.equal(isRecentlyCreatedPlan({ created_at: "" }, now), false);
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

test("splitLabeledSegments breaks a packed body line into labelled details", () => {
  const segments = splitLabeledSegments(
    "Purpose: raise the base. Progress/regress: add 5 min. Stop rule: stop if dizzy.",
  );

  assert.deepEqual(segments, [
    { label: "Purpose", text: "raise the base." },
    { label: "Progress", text: "add 5 min." },
    { label: "Stop", text: "stop if dizzy." },
  ]);
});

test("splitLabeledSegments returns one unlabelled segment when no labels are present", () => {
  assert.deepEqual(splitLabeledSegments("Easy Assault Bike — 25 min Zone 2."), [
    { label: null, text: "Easy Assault Bike — 25 min Zone 2." },
  ]);
});

test("legacy plan text parses into notes, week and session groups", () => {
  const groups = parsePlanText(
    [
      "Lead notes",
      "- Injury: keep cut covered.",
      "",
      "GPP — Week 1 (D-33 to D-27) — Build aerobic base",
      "D-33 (Wednesday) — Aerobic support",
      "Why: restore repeatability.",
      "Easy Assault Bike — 25 min Zone 2. Keep nasal breathing.",
      "Purpose: raise the base. Progress/regress: add 5 min. Stop rule: stop if dizzy.",
      "",
      "Final notes",
      "Stop on dizziness.",
    ].join("\n"),
  );

  assert.deepEqual(
    groups.map((group) => group.kind),
    ["notes", "week", "notes"],
  );

  const [lead, week, final] = groups;
  assert.equal(lead.kind === "notes" && lead.title, "Lead notes");
  assert.deepEqual(lead.kind === "notes" ? lead.lines : null, ["Injury: keep cut covered."]);
  assert.equal(final.kind === "notes" && final.title, "Final notes");

  assert.ok(week.kind === "week");
  assert.equal(week.phase, "GPP");
  assert.equal(week.title, "Week 1 (D-33 to D-27) — Build aerobic base");
  assert.equal(week.sessions.length, 1);

  const session = week.sessions[0];
  assert.equal(session.countdown, "D-33");
  assert.equal(session.weekday, "Wednesday");
  assert.equal(session.title, "Aerobic support");
  assert.equal(session.objective, "restore repeatability.");
  assert.equal(session.blocks.length, 1);
  assert.equal(session.blocks[0].name, "Easy Assault Bike");
  assert.equal(session.blocks[0].dose, "25 min Zone 2. Keep nasal breathing.");
  assert.deepEqual(session.blocks[0].details, [
    { label: "Purpose", text: "raise the base." },
    { label: "Progress", text: "add 5 min." },
    { label: "Stop", text: "stop if dizzy." },
  ]);
});

test("session headers parse in both countdown-first and weekday-first forms with any separator", () => {
  const groups = parsePlanText(
    [
      "GPP — Week 1 (D-33 to D-27) — Build aerobic base",
      "D-33 (Wednesday) — Aerobic support",
      "Why: easy day.",
      "Wednesday (D-32) - Strength",
      "Why: build force.",
      "D-0 (Saturday): Fight day",
      "Why: compete.",
    ].join("\n"),
  );

  const week = groups[0];
  assert.ok(week.kind === "week");
  assert.equal(week.phase, "GPP");
  assert.deepEqual(
    week.sessions.map((session) => [session.countdown, session.weekday, session.title]),
    [
      ["D-33", "Wednesday", "Aerobic support"],
      ["D-32", "Wednesday", "Strength"],
      ["D-0", "Saturday", "Fight day"],
    ],
  );
});

test("inline Why/coach metadata on a run-on session heading is split into body, not the title", () => {
  const groups = parsePlanText(
    "GPP — Week 1 (D-33 to D-27) — Build base D-33 (Wednesday) — Aerobic support Why: restore repeatability. D-32 (Thursday) — Coach-led boxing session No app S&C today. Keep freshness.",
  );

  const week = groups[0];
  assert.ok(week.kind === "week");
  const [aerobic, coach] = week.sessions;
  assert.equal(aerobic.title, "Aerobic support");
  assert.equal(aerobic.objective, "restore repeatability.");
  assert.equal(coach.title, "Coach-led boxing session");
  assert.match(coach.coachNote ?? "", /No app S&C today/);
  assert.equal(coach.blocks.length, 0);
});

test("labeled session-level notes keep their label", () => {
  const groups = parsePlanText(
    ["D-20 (Tuesday) — Conditioning", "Note: keep it light today."].join("\n"),
  );

  const session = groups[0];
  assert.ok(session.kind === "session");
  assert.deepEqual(session.notes, ["Note: keep it light today."]);
});

test("markdown section headers (## Nutrition) become their own context cards", () => {
  const groups = parsePlanText(["## Nutrition", "Eat to support training.", "## Recovery", "Sleep 8h."].join("\n"));

  assert.deepEqual(
    groups.map((group) => [group.kind, group.kind === "notes" ? group.title : null]),
    [
      ["notes", "Nutrition"],
      ["notes", "Recovery"],
    ],
  );
});

test("coach-led session keeps its freshness note instead of a block", () => {
  const groups = parsePlanText(
    [
      "GPP — Week 1 (D-33 to D-27) — Build aerobic base",
      "D-32 (Thursday) — Coach-led boxing session",
      "Coach-led boxing session No app S&C today. Keep freshness priority.",
    ].join("\n"),
  );

  const week = groups[0];
  assert.ok(week.kind === "week");
  const session = week.sessions[0];
  assert.equal(session.title, "Coach-led boxing session");
  assert.equal(session.blocks.length, 0);
  assert.match(session.coachNote ?? "", /No app S&C today/);
});
