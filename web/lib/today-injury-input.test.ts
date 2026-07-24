import assert from "node:assert/strict";
import test from "node:test";

import {
  TODAY_INJURY_TYPE_OPTIONS,
  composeTodayInjuryDescription,
} from "./today-injury-input.ts";

test("only minor, non-escalating types plus Other are offered", () => {
  assert.deepEqual(
    TODAY_INJURY_TYPE_OPTIONS.map((option) => option.value),
    ["soreness", "tightness", "bruise", "other"],
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
