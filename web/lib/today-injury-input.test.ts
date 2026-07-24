import assert from "node:assert/strict";
import test from "node:test";

import {
  NO_TODAY_INJURY_TYPE,
  TODAY_INJURY_TYPE_OPTIONS,
  composeTodayInjuryDescription,
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

test("limitInjuryEntryText keeps entries within the word and character caps", () => {
  // Under both caps: passed through unchanged.
  assert.equal(limitInjuryEntryText("left shoulder"), "left shoulder");
  // Exactly 3 words is allowed.
  assert.equal(limitInjuryEntryText("left shoulder bruise"), "left shoulder bruise");
  // A 4th word is dropped.
  assert.equal(limitInjuryEntryText("left shoulder bruise ache"), "left shoulder bruise");
  // A trailing space while under the word cap is preserved (next word can start).
  assert.equal(limitInjuryEntryText("left "), "left ");
});

test("limitInjuryEntryText caps at 30 characters", () => {
  const long = "abcdefghij klmnopqrst uvwxyzabcd"; // 31 chars, 3 words
  const result = limitInjuryEntryText(long);
  assert.equal(result.length, 30);
  assert.equal(result, "abcdefghij klmnopqrst uvwxyzab");
});
