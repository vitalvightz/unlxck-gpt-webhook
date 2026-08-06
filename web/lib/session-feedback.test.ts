import test from "node:test";
import assert from "node:assert/strict";

import {
  SESSION_DIFFICULTY_OPTIONS,
  SESSION_INSTRUCTIONS_OPTIONS,
  SESSION_PLAN_ACCURACY_OPTIONS,
  hasSessionFeedbackContent,
  shouldPromptSessionFeedback,
} from "@/lib/session-feedback";

test("a trained session is prompted for review", () => {
  assert.equal(shouldPromptSessionFeedback("done"), true);
  assert.equal(shouldPromptSessionFeedback("modified"), true);
});

test("a session that was not trained is never prompted", () => {
  assert.equal(shouldPromptSessionFeedback("skipped"), false);
  assert.equal(shouldPromptSessionFeedback("started"), false);
  assert.equal(shouldPromptSessionFeedback("not_started"), false);
  assert.equal(shouldPromptSessionFeedback(null), false);
});

test("a single answer is enough to submit", () => {
  assert.equal(hasSessionFeedbackContent({ difficulty: "too_hard" }, "", null), true);
  assert.equal(hasSessionFeedbackContent({ instructions: "unclear" }, "", null), true);
  assert.equal(hasSessionFeedbackContent({ plan_accuracy: "felt_right" }, "", null), true);
});

test("a comment or a screenshot alone is enough to submit", () => {
  assert.equal(hasSessionFeedbackContent({}, "The warm-up was missing", null), true);
  assert.equal(
    hasSessionFeedbackContent({}, "", new File(["x"], "shot.png", { type: "image/png" })),
    true,
  );
});

test("an untouched prompt cannot be submitted", () => {
  assert.equal(hasSessionFeedbackContent({}, "", null), false);
  assert.equal(hasSessionFeedbackContent({}, "   \n ", null), false);
});

test("the offered choices match the three questions the prompt asks", () => {
  assert.deepEqual(
    SESSION_DIFFICULTY_OPTIONS.map(([, value]) => value),
    ["too_easy", "appropriate", "too_hard"],
  );
  assert.deepEqual(
    SESSION_INSTRUCTIONS_OPTIONS.map(([, value]) => value),
    ["clear", "unclear"],
  );
  assert.deepEqual(
    SESSION_PLAN_ACCURACY_OPTIONS.map(([, value]) => value),
    ["felt_right", "something_wrong"],
  );
});
