import test from "node:test";
import assert from "node:assert/strict";

import { ApiError } from "@/lib/api";
import {
  classifyGenerationFailure,
  describeGenerationFailure,
  humanizeGenerationError,
  isRetryableGenerationFailure,
  STALLED_GENERATION_ERROR,
} from "./generation-failure";

test("a build that never reached the server is start_failed, and retryable", () => {
  // The old screen offered no retry here at all — the most retryable failure
  // there is (the request never landed) was the one with no "Try again".
  const kind = classifyGenerationFailure(new Error("Connection issue. Try again in a minute."), {
    hasFailedJobId: false,
  });
  assert.equal(kind, "start_failed");
  assert.equal(isRetryableGenerationFailure(kind), true);
});

test("a server job that reached failed is job_failed, and retryable", () => {
  const kind = classifyGenerationFailure(new Error("Plan generation failed unexpectedly."), {
    hasFailedJobId: true,
  });
  assert.equal(kind, "job_failed");
  assert.equal(isRetryableGenerationFailure(kind), true);
});

test("a stalled watch is classified before anything else", () => {
  assert.equal(
    classifyGenerationFailure(new Error(STALLED_GENERATION_ERROR), { hasFailedJobId: true }),
    "stalled",
  );
});

test("a rejected intake is never offered a retry", () => {
  const kind = classifyGenerationFailure(
    new Error("invalid Weekly Training Frequency: cannot exceed selected Training Availability days"),
    { hasFailedJobId: true },
  );
  assert.equal(kind, "invalid_intake");
  assert.equal(isRetryableGenerationFailure(kind), false);
  assert.equal(describeGenerationFailure(kind, "Pick more training days.").primary, "refine_intake");
});

test("4xx responses map to non-retryable kinds", () => {
  assert.equal(classifyGenerationFailure(new ApiError("Too many requests", 429)), "limit_reached");
  assert.equal(classifyGenerationFailure(new ApiError("Bad payload", 422)), "invalid_intake");
  assert.equal(classifyGenerationFailure(new ApiError("Conflict", 409)), "unavailable");
  assert.equal(isRetryableGenerationFailure("limit_reached"), false);
  assert.equal(isRetryableGenerationFailure("unavailable"), false);
});

test("an in-flight conflict is a limit, not an intake problem", () => {
  assert.equal(
    classifyGenerationFailure(
      new Error("A generation job is already queued or running for this account."),
      { hasFailedJobId: false },
    ),
    "limit_reached",
  );
});

test("every failure kind offers a way out of the screen", () => {
  const kinds = [
    "job_failed",
    "stalled",
    "start_failed",
    "invalid_intake",
    "limit_reached",
    "unavailable",
  ] as const;

  kinds.forEach((kind) => {
    const copy = describeGenerationFailure(kind, "Plan generation failed unexpectedly.");
    const actions = [copy.primary, ...copy.secondary];
    assert.ok(copy.headline.length > 0, `${kind} needs a headline`);
    assert.ok(copy.detail.length > 0, `${kind} needs a detail`);
    assert.ok(
      actions.includes("workspace") || actions.includes("plan_history"),
      `${kind} must leave an exit from the failure screen`,
    );
    // Retry is only ever the recommended action for a kind a retry can fix.
    assert.equal(copy.primary === "retry", isRetryableGenerationFailure(kind), `${kind} primary action`);
  });
});

test("engineering error text never reaches the athlete verbatim", () => {
  assert.equal(
    humanizeGenerationError("Stage 2 first_pass prompt too large: 214880 chars"),
    "Your camp was too large to finalize in one pass. A retry usually clears it.",
  );
  assert.equal(
    humanizeGenerationError("Cancelled by athlete."),
    "This build was cancelled before it finished.",
  );
  assert.equal(humanizeGenerationError(null), "The build stopped before a plan was saved.");
  assert.equal(
    humanizeGenerationError("KeyError: 'weekly_structure'"),
    "The build stopped before a plan was saved.",
  );
});

test("athlete-ready backend messages pass through unchanged", () => {
  const capMessage = "You have reached the daily plan generation limit. It resets at midnight.";
  assert.equal(humanizeGenerationError(capMessage), capMessage);
});
