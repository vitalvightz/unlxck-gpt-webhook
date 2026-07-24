import assert from "node:assert/strict";
import test from "node:test";

import {
  NO_TODAY_INJURY_TYPE,
  TODAY_INJURY_TYPE_OPTIONS,
  composeTodayInjuryDescription,
  isInjuryEntryLimited,
  limitInjuryEntryText,
} from "./today-injury-input.ts";

test("only minor, non-escalating types plus Other are offered", () => {
  assert.deepEqual(
    TODAY_INJURY_TYPE_OPTIONS.map((option) => option.value),
    ["soreness", "tightness", "bruise", "other"],
  );
});

test("the unselected sentinel is not a selectable option (type must be chosen)", () => {
  assert.equal(NO_TODAY_INJURY_TYPE, "");
  assert.ok(
    !TODAY_INJURY_TYPE_OPTIONS.some((option) => option.value === NO_TODAY_INJURY_TYPE),
    "empty selection must never be a tappable type",
  );
});

test("composes the type word ahead of the detail so the scorer reads both", () => {
  assert.equal(
    composeTodayInjuryDescription({ injuryType: "soreness", detail: "tight after sprinting" }),
    "soreness. tight after sprinting",
  );
});

test("a bare type tap becomes just the condition word", () => {
  assert.equal(composeTodayInjuryDescription({ injuryType: "bruise", detail: "" }), "bruise");
});

test("Other injects no condition word — detail carries the report", () => {
  assert.equal(
    composeTodayInjuryDescription({ injuryType: "other", detail: "feels unstable" }),
    "feels unstable",
  );
});

test("Other with no detail yields an empty description (body-map location stands alone)", () => {
  assert.equal(composeTodayInjuryDescription({ injuryType: "other", detail: "" }), "");
});

test("detail whitespace is collapsed and trimmed", () => {
  assert.equal(
    composeTodayInjuryDescription({ injuryType: "tightness", detail: "  eased   overnight  " }),
    "tightness. eased overnight",
  );
});

test("limitInjuryEntryText allows real 4-word locations", () => {
  assert.equal(limitInjuryEntryText("left shoulder"), "left shoulder");
  // 4 words is allowed, so the body part is never lost.
  assert.equal(limitInjuryEntryText("back of left knee"), "back of left knee");
  assert.equal(limitInjuryEntryText("outside of right ankle"), "outside of right ankle");
  // A 5th word is dropped.
  assert.equal(limitInjuryEntryText("back of left knee area"), "back of left knee");
  // A trailing space while under the word cap is preserved (next word can start).
  assert.equal(limitInjuryEntryText("left "), "left ");
});

test("limitInjuryEntryText caps at 40 characters on a word boundary", () => {
  // Four 10-char words = 43 chars > 40; the 4th word is dropped whole, not cut.
  const input = "aaaaaaaaaa bbbbbbbbbb cccccccccc dddddddddd";
  const result = limitInjuryEntryText(input);
  assert.ok(result.length <= 40, `expected <=40, got ${result.length}`);
  assert.equal(result, "aaaaaaaaaa bbbbbbbbbb cccccccccc");
  // A single word longer than the cap has no boundary, so it is hard-cut.
  assert.equal(limitInjuryEntryText("x".repeat(45)).length, 40);
});

test("isInjuryEntryLimited flags only entries that were actually trimmed", () => {
  assert.equal(isInjuryEntryLimited("back of left knee"), false);
  assert.equal(isInjuryEntryLimited("back of left knee area"), true);
});
