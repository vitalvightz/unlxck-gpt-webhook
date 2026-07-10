import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  buildStructuredPlanFromText,
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
  readStructuredCardDebug,
  resolveApprovalAfterError,
  shouldAwaitStructuredPlanUpgrade,
  shouldPollForStructuredPlanUpgrade,
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

test("stage2 failed without validator reasons or blockers is still releasable", () => {
  const summary = buildReviewSummary({}, "stage2_failed", {
    hasBlockedTriageStubText: false,
  });

  assert.equal(summary.isPublishable, true);
  assert.equal(summary.hasIssues, false);
  assert.equal(summary.blockingCount, 0);
  assert.match(summary.headline, /ready to release/i);
});

test("blocked triage stub without validator reasons still explains the hold", () => {
  const summary = buildReviewSummary({}, "stage2_failed", {
    hasBlockedTriageStubText: true,
  });

  assert.equal(summary.isPublishable, false);
  assert.equal(summary.hasIssues, true);
  assert.equal(summary.blockingCount, 0);
  assert.match(summary.headline, /Triage placeholder text/i);
  assert.match(summary.guidance, /cannot be released/i);
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

test("recent published plan without structured card awaits the background upgrade", () => {
  assert.equal(
    shouldAwaitStructuredPlanUpgrade({
      hasPublishedPlan: true,
      hasStructuredPlan: false,
      pollWindowExpired: false,
      hasAccessToken: true,
      isRecentPlan: true,
    }),
    true,
  );
});

test("structured card or an elapsed poll window stops awaiting the upgrade", () => {
  assert.equal(
    shouldAwaitStructuredPlanUpgrade({
      hasPublishedPlan: true,
      hasStructuredPlan: true,
      pollWindowExpired: false,
      hasAccessToken: true,
      isRecentPlan: true,
    }),
    false,
  );
  assert.equal(
    shouldAwaitStructuredPlanUpgrade({
      hasPublishedPlan: true,
      hasStructuredPlan: false,
      pollWindowExpired: true,
      hasAccessToken: true,
      isRecentPlan: true,
    }),
    false,
  );
});

test("triage blocked plans do not await a structured-card upgrade", () => {
  assert.equal(
    shouldAwaitStructuredPlanUpgrade({
      hasPublishedPlan: true,
      hasStructuredPlan: false,
      pollWindowExpired: false,
      hasAccessToken: true,
      isRecentPlan: true,
      isTriageBlocked: true,
    }),
    false,
  );
});

test("legacy plans without a structured card do not await an upgrade", () => {
  assert.equal(
    shouldAwaitStructuredPlanUpgrade({
      hasPublishedPlan: true,
      hasStructuredPlan: false,
      pollWindowExpired: false,
      hasAccessToken: true,
      isRecentPlan: false,
    }),
    false,
  );
});

test("plans without an access token cannot await a structured upgrade", () => {
  assert.equal(
    shouldAwaitStructuredPlanUpgrade({
      hasPublishedPlan: true,
      hasStructuredPlan: false,
      pollWindowExpired: false,
      hasAccessToken: false,
      isRecentPlan: true,
    }),
    false,
  );
});

test("the upgrade poll keeps running for an older published plan still missing its card", () => {
  // The key fix: a plan whose card lands after the 5-minute recency window (e.g.
  // approved several minutes after generation) must still auto-swap on an open
  // view. The poll is NOT recency-gated, unlike the visible hint.
  assert.equal(
    shouldPollForStructuredPlanUpgrade({
      hasPublishedPlan: true,
      hasStructuredPlan: false,
      pollWindowExpired: false,
      hasAccessToken: true,
    }),
    true,
  );
  // But it stops once the card exists, the mount-scoped window elapses, the plan
  // isn't published, the token is missing, or the plan is triage-blocked.
  assert.equal(
    shouldPollForStructuredPlanUpgrade({
      hasPublishedPlan: true,
      hasStructuredPlan: true,
      pollWindowExpired: false,
      hasAccessToken: true,
    }),
    false,
  );
  assert.equal(
    shouldPollForStructuredPlanUpgrade({
      hasPublishedPlan: true,
      hasStructuredPlan: false,
      pollWindowExpired: true,
      hasAccessToken: true,
    }),
    false,
  );
  assert.equal(
    shouldPollForStructuredPlanUpgrade({
      hasPublishedPlan: true,
      hasStructuredPlan: false,
      pollWindowExpired: false,
      hasAccessToken: true,
      isTriageBlocked: true,
    }),
    false,
  );
});

test("readStructuredCardDebug surfaces every recorded outcome and sanitises reasons", () => {
  const make = (structured: unknown) =>
    ({ admin_outputs: { stage2_validator_report: { structured_plan: structured } } }) as never;

  // A rejected conversion is shown with its drift reasons.
  assert.deepEqual(
    readStructuredCardDebug(
      make({ status: "invalid_fallback_used", errors: ["faithfulness: exercise 'X' not present in source text"] }),
    ),
    { status: "invalid_fallback_used", errors: ["faithfulness: exercise 'X' not present in source text"] },
  );
  // A `valid`/`repair_attempted_valid` status on the fallback IS the signal we
  // want (card built then lost), so it must surface — not be hidden.
  assert.deepEqual(readStructuredCardDebug(make({ status: "valid", errors: [] })), {
    status: "valid",
    errors: [],
  });
  assert.deepEqual(readStructuredCardDebug(make({ status: "repair_attempted_valid" })), {
    status: "repair_attempted_valid",
    errors: [],
  });
  // null/undefined/whitespace-only reasons are dropped, never shown as rubbish.
  assert.deepEqual(
    readStructuredCardDebug(
      make({ status: "invalid_fallback_used", errors: [null, undefined, "   ", "real reason"] }),
    ),
    { status: "invalid_fallback_used", errors: ["real reason"] },
  );
  // Nothing recorded (no debug, blank status, or no admin outputs) → nothing to show.
  assert.equal(readStructuredCardDebug(make(undefined)), null);
  assert.equal(readStructuredCardDebug(make({ status: "   " })), null);
  assert.equal(readStructuredCardDebug({ admin_outputs: null } as never), null);
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

test("compact labelled late-camp output parses into clean session blocks", () => {
  const groups = parsePlanText(
    [
      "D-18 (Wednesday) — Power Transfer Touch",
      "Why: one meaningful strength touch early in the bridge window.",
      "- Movement prep (4 min): ankle/hip swings, 2 min easy shadow jab-cross with rhythm.",
      "- Band-Resisted Jab-Cross Primer — 3 x 4-6 reps per side; full recovery 90-120 s; intensity: RPE 6-7.",
      "Purpose: preserve punch speed and transfer strength with minimal metabolic cost.",
      "Why today: one meaningful strength touch early in the bridge window.",
      "Progression/regression/stop: reduce band tension if technique breaks.",
      "- Reset (2-3 min): slow mobility flow for hips and thoracic rotation.",
    ].join("\n"),
  );

  const session = groups[0];
  assert.ok(session.kind === "session");
  assert.equal(session.title, "Power Transfer Touch");
  assert.equal(session.objective, "one meaningful strength touch early in the bridge window.");
  assert.deepEqual(
    session.blocks.map((block) => [block.name, block.dose]),
    [
      [
        "Movement prep (4 min)",
        "ankle/hip swings, 2 min easy shadow jab-cross with rhythm.",
      ],
      [
        "Band-Resisted Jab-Cross Primer",
        "3 x 4-6 reps per side; full recovery 90-120 s; intensity: RPE 6-7.",
      ],
      ["Reset (2-3 min)", "slow mobility flow for hips and thoracic rotation."],
    ],
  );
  assert.deepEqual(session.blocks[1].details, [
    { label: "Purpose", text: "preserve punch speed and transfer strength with minimal metabolic cost." },
    { label: "Why", text: "one meaningful strength touch early in the bridge window." },
    { label: "Progress", text: "reduce band tension if technique breaks." },
  ]);
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

test("rehab bullet items parse into clean blocks tagged by their sub-heading", () => {
  const groups = parsePlanText(
    [
      "D-44 (Friday) — Soft work",
      "Rehab",
      "• Soft-tissue ball on anterior/lateral deltoid — 2 x 60s (gentle)",
      "Purpose: local tissue desensitisation for the bruise area.",
      "• Banded IR/ER light pulses — 2 x 10 each side, very light band",
      "Purpose: reintroduce gentle rotator control with minimal load.",
    ].join("\n"),
  );

  const session = groups[0];
  assert.ok(session.kind === "session");
  // The bare "Rehab" sub-heading becomes a block tag, never a stray note.
  assert.ok(!session.notes.includes("Rehab"));
  assert.deepEqual(
    session.blocks.map((block) => [block.name, block.dose, block.tag]),
    [
      ["Soft-tissue ball on anterior/lateral deltoid", "2 x 60s (gentle)", "Rehab"],
      ["Banded IR/ER light pulses", "2 x 10 each side, very light band", "Rehab"],
    ],
  );
  // The "•" glyph never leaks into an exercise title.
  assert.ok(session.blocks.every((block) => !block.name.includes("•")));
  // Labelled detail still attaches to its block.
  assert.deepEqual(session.blocks[0].details, [
    { label: "Purpose", text: "local tissue desensitisation for the bruise area." },
  ]);
});

test("a block-group sub-heading tags only its own session and does not bleed into the next", () => {
  const groups = parsePlanText(
    [
      "D-43 (Saturday) — Easy day",
      "Mobility",
      "• Thoracic opener — 2 x 8",
      "D-42 (Sunday) — Bike",
      "Easy Assault Bike — 20 min Zone 2",
    ].join("\n"),
  );

  const [first, second] = groups;
  assert.ok(first.kind === "session" && second.kind === "session");
  assert.equal(first.blocks[0].name, "Thoracic opener");
  assert.equal(first.blocks[0].tag, "Mobility");
  // The next session starts with no inherited tag.
  assert.equal(second.blocks[0].name, "Easy Assault Bike");
  assert.equal(second.blocks[0].tag, null);
});

test("missing saved structure is adapted into the full structured renderer contract", () => {
  const plan = buildStructuredPlanFromText(
    [
      "Lead notes",
      "- Protect freshness through the bridge window.",
      "",
      "TAPER - Week 1 (D-21 to D-15) - Sharpen",
      "D-21 (Thursday) - Power Transfer Touch",
      "Why: preserve punch speed without soreness.",
      "Band-Resisted Jab-Cross Primer - 4 x 4 reps; RPE 7.",
      "Purpose: transfer force into the jab-cross. Progress: add one set. Stop: stop if technique breaks.",
    ].join("\n"),
    "2026-07-23",
  );

  assert.equal(plan.schema_version, "text-adapter.v1");
  assert.equal(plan.raw_markdown_fallback?.includes("Power Transfer Touch"), true);
  assert.equal(plan.plan_notes?.[0]?.text, "Protect freshness through the bridge window.");
  assert.equal(plan.weeks?.length, 1);

  const week = plan.weeks?.[0];
  assert.equal(week?.phase_label, "TAPER");
  assert.equal(week?.week_index, 1);
  assert.equal(week?.days?.[0]?.date, "2026-07-02");
  assert.equal(week?.days?.[0]?.countdown_label, "D-21");

  const session = week?.days?.[0]?.sessions?.[0];
  assert.equal(session?.title, "Power Transfer Touch");
  assert.equal(session?.objective, "preserve punch speed without soreness.");
  assert.equal(session?.session_type, "strength_power");
  assert.equal(session?.blocks?.[0]?.display_name, "Band-Resisted Jab-Cross Primer");
  assert.equal(session?.blocks?.[0]?.load?.display, "4 x 4 reps; RPE 7.");
  assert.equal(session?.blocks?.[0]?.purpose, "transfer force into the jab-cross.");
  assert.equal(session?.blocks?.[0]?.progression_rule, "add one set.");
  assert.deepEqual(session?.blocks?.[0]?.coaching_cues, ["Stop: stop if technique breaks."]);
});

test("coach-only plan text remains a visible enhanced day card", () => {
  const plan = buildStructuredPlanFromText(
    [
      "SPP - Week 2",
      "D-16 (Tuesday) - Coach-led boxing - technical only",
      "No app S&C today. Keep freshness priority.",
    ].join("\n"),
    "2026-07-23",
  );

  const day = plan.weeks?.[0]?.days?.[0];
  assert.equal(day?.date, "2026-07-07");
  assert.equal(day?.today_card?.headline, "Coach-led boxing - technical only");
  assert.deepEqual(day?.sessions, []);
});

test("the no-payload branch mounts StructuredPlanRenderer instead of legacy cards", () => {
  const adapterComponent = PLAN_VIEWER_SOURCE.slice(
    PLAN_VIEWER_SOURCE.indexOf("function TextStructuredPlanRenderer"),
    PLAN_VIEWER_SOURCE.indexOf("export type StructuredCardDebug"),
  );

  assert.equal(adapterComponent.includes("<StructuredPlanRenderer"), true);
  assert.equal(adapterComponent.includes("legacy-plan-root"), false);
  assert.equal(adapterComponent.includes("legacy-plan-card-stack"), false);
});
