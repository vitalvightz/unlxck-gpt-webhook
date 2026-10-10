import assert from "node:assert/strict";
import test from "node:test";

import {
  NO_TODAY_INJURY_TYPE,
  TODAY_INJURY_TYPE_OPTIONS,
  composeTodayInjuryDescription,
  isInjuryEntryLimited,
  limitInjuryEntryText,
  readElbowSite, stripElbowSite, writeElbowSite,
} from "./today-injury-input.ts";

test("elbow location remains explicit and editing replaces rather than duplicates it", () => {
  assert.equal(readElbowSite("lateral elbow tendonitis"), "unknown");
  assert.equal(readElbowSite("[elbow_site:lateral] [elbow_site:unknown]"), "unknown");
  const saved = writeElbowSite("tendonitis [elbow_site:other]", "lateral");
  assert.equal(saved, "tendonitis [elbow_site:lateral]");
  assert.equal(readElbowSite(saved), "lateral");
  assert.equal(stripElbowSite(saved), "tendonitis");
});

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

test("ankle applicability requires one explicit clinician-described answer and replaces stale markers", async () => {
  const { readAnkleScope, stripAnkleScope, writeAnkleScope } = await import("./today-injury-input.ts");
  assert.equal(readAnkleScope("outer ankle sprain"), "unknown");
  assert.equal(readAnkleScope("sprain [ankle_scope:uncomplicated_lateral]"), "uncomplicated_lateral");
  assert.equal(readAnkleScope("[ankle_scope:uncomplicated_lateral] [ankle_scope:other]"), "unknown");
  assert.equal(readAnkleScope("[ankle_scope:made_up]"), "unknown");
  assert.equal(stripAnkleScope("sprain [ankle_scope:unknown]"), "sprain");
  assert.equal(writeAnkleScope("sprain [ankle_scope:uncomplicated_lateral]", "other"), "sprain [ankle_scope:other]");
});

test("Other types follow the area and write a word the scorer recognises", async () => {
  const { getTodayOtherInjuryTypes, readTodayOtherInjuryType, TODAY_OTHER_INJURY_TYPES } = await import("./today-injury-input.ts");
  assert.deepEqual(getTodayOtherInjuryTypes("Left knee").suggested,
    ["sprain", "swelling", "instability", "stiffness", "hyperextension", "dislocation", "fracture"]);
  assert.ok(getTodayOtherInjuryTypes("Right shoulder").suggested.includes("impingement"));
  assert.equal(getTodayOtherInjuryTypes("Head / Neck").suggested[0], "concussion");
  assert.ok(getTodayOtherInjuryTypes("Ribs").suggested.includes("fracture"));
  assert.ok(getTodayOtherInjuryTypes("Left hand").skin.includes("blister"));
  assert.ok(!getTodayOtherInjuryTypes("Left quad").skin.includes("blister"));
  assert.ok(getTodayOtherInjuryTypes("somewhere odd").suggested.length >= 8);

  assert.equal(composeTodayInjuryDescription({ injuryType: "other", otherType: "sprain", detail: "rolled it" }), "sprain. rolled it");
  assert.equal(composeTodayInjuryDescription({ injuryType: "other", otherType: "nerve", detail: "" }), "numbness and tingling");
  assert.equal(composeTodayInjuryDescription({ injuryType: "other", otherType: "", detail: "odd ache" }), "odd ache");
  assert.equal(readTodayOtherInjuryType("fracture. fell on it"), "fracture");
  assert.equal(readTodayOtherInjuryType("numbness and tingling"), "nerve");
  assert.equal(readTodayOtherInjuryType("odd ache after a sprain"), "");
  assert.ok(Object.values(TODAY_OTHER_INJURY_TYPES).filter((type) => type.serious).length === 4);
});
