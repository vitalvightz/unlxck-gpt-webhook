import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  UNSAFE_GUIDANCE,
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
