import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  THUMB_PATHS,
  UNSAFE_GUIDANCE,
  buildContextualFeedbackPayload,
  shouldShowUnsafeGuidance,
} from "./contextual-feedback";

const CONTEXTUAL_SOURCE = readFileSync(new URL("./contextual-feedback.tsx", import.meta.url), "utf8");
const GLOBAL_SOURCE = readFileSync(new URL("./global-feedback.tsx", import.meta.url), "utf8");

test("unsafe guidance is visible from selection through the saved state", () => {
  assert.equal(shouldShowUnsafeGuidance("unsafe", null), true);
  assert.equal(shouldShowUnsafeGuidance(null, "unsafe"), true);
  assert.equal(shouldShowUnsafeGuidance("no", "no"), false);
  assert.equal(
    UNSAFE_GUIDANCE,
    "Do not continue this recommendation if it feels unsafe. Update your injury or readiness information and seek qualified medical help when necessary.",
  );
});

test("contextual feedback contains the exact beta questions and reason codes", () => {
  assert.match(CONTEXTUAL_SOURCE, /Is this plan useful\?/);
  assert.match(CONTEXTUAL_SOURCE, /Did this recommendation fit how you feel today\?/);
  for (const code of [
    "too_hard",
    "too_easy",
    "schedule_mismatch",
    "injury_restrictions_wrong",
    "exercises_unsuitable",
    "instructions_unclear",
    "other",
    "too_demanding",
    "too_cautious",
    "pain_or_injury_ignored",
    "training_mismatch",
    "repetitive",
    "unclear",
  ]) {
    assert.ok(CONTEXTUAL_SOURCE.includes(`\"${code}\"`), `missing ${code}`);
  }
  assert.match(CONTEXTUAL_SOURCE, /Feedback sent/);
  assert.match(CONTEXTUAL_SOURCE, /Change response/);
});

test("feedback choices use explicit correctly oriented thumb icons", () => {
  assert.match(THUMB_PATHS.up, /^M7 10v10/);
  assert.match(THUMB_PATHS.down, /^M7 14V4/);
  assert.match(CONTEXTUAL_SOURCE, /<ThumbIcon direction="up" \/> Yes/);
  assert.match(CONTEXTUAL_SOURCE, /<ThumbIcon direction="down" \/> \{isPlan \? "Needs improvement" : "No"\}/);
});

test("feedback controls render without waiting for the existing-response request", () => {
  assert.doesNotMatch(CONTEXTUAL_SOURCE, /FeedbackLoadState|Loading feedback|Feedback couldn’t load|>\s*Retry\s*</);
  assert.match(CONTEXTUAL_SOURCE, /getPlanFeedback|getTodayFeedback/);
  assert.match(CONTEXTUAL_SOURCE, /userInteractedRef\.current/);
  assert.match(CONTEXTUAL_SOURCE, /if \(!active \|\| !saved \|\| userInteractedRef\.current\) return/);
  assert.match(CONTEXTUAL_SOURCE, /record && !editing/);
});

test("submission failures remain separate from feedback loading", () => {
  assert.match(CONTEXTUAL_SOURCE, /setSubmissionError\(saveError instanceof Error/);
  assert.match(CONTEXTUAL_SOURCE, /submissionError \? <p className="feedback-error" role="alert">/);
});

test("global attachment privacy copy is explicit and adjacent to the control", () => {
  assert.match(
    GLOBAL_SOURCE,
    /Avoid uploading screenshots containing private messages, contact details, payment information, or unrelated health information\./,
  );
  assert.match(
    GLOBAL_SOURCE,
    /Sanitisation removes metadata\. It does not remove sensitive information visible inside the image\./,
  );
  assert.ok(GLOBAL_SOURCE.indexOf("global-feedback-screenshot") < GLOBAL_SOURCE.indexOf("Avoid uploading"));
});

test("changing a negative response to yes clears its reason and complaint", () => {
  const negative = buildContextualFeedbackPayload("no", "too_hard", "Volume was too high");
  assert.deepEqual(negative, {
    response: "no",
    reason: "too_hard",
    comment: "Volume was too high",
  });

  const revised = buildContextualFeedbackPayload("yes", negative.reason ?? null, negative.comment ?? "");
  assert.deepEqual(revised, {
    response: "yes",
    reason: null,
    comment: "",
  });
});

test("global attachment control includes preview details and explicit removal", () => {
  assert.match(GLOBAL_SOURCE, /URL\.createObjectURL/);
  assert.match(GLOBAL_SOURCE, /URL\.revokeObjectURL/);
  assert.match(GLOBAL_SOURCE, /Selected screenshot preview/);
  assert.match(GLOBAL_SOURCE, /Remove image/);
  assert.match(GLOBAL_SOURCE, /fileInputRef\.current\.value = ""/);
});
