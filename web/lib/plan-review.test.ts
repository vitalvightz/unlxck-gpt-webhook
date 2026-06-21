import test from "node:test";
import assert from "node:assert/strict";

import { getPlanReviewReason, isHeldForAdminReviewPlan } from "./plan-review.ts";

test("held and legacy review-required statuses are admin-review holds", () => {
  assert.equal(isHeldForAdminReviewPlan({ status: "held_for_review" }), true);
  assert.equal(isHeldForAdminReviewPlan({ status: "review_required" }), true);
  assert.equal(isHeldForAdminReviewPlan({ status: "ready" }), false);
});

test("held plan review reason prefers backend reason", () => {
  assert.equal(
    getPlanReviewReason({
      status: "held_for_review",
      review_reason: "Stage 2 validation found blocking issues.",
    }),
    "Stage 2 validation found blocking issues.",
  );
});

test("non-held plans do not show a review reason", () => {
  assert.equal(
    getPlanReviewReason({
      status: "ready",
      review_reason: "Should not render.",
    }),
    null,
  );
});
