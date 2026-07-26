import assert from "node:assert/strict";
import test from "node:test";

import { normalizeInjuryLabel } from "./injury-display.ts";

test("normalizes a literal bruise sentence into a short label", () => {
  assert.equal(normalizeInjuryLabel("Left shoulder is bruised"), "Left shoulder bruise");
});

test("maps 'pulled' to a strain and keeps laterality", () => {
  assert.equal(normalizeInjuryLabel("pulled right hamstring"), "Right hamstring strain");
});

test("maps contusion to bruise", () => {
  assert.equal(normalizeInjuryLabel("right quad contusion"), "Right quad bruise");
});

test("normalizes sprain phrasing", () => {
  assert.equal(normalizeInjuryLabel("Left ankle sprained"), "Left ankle sprain");
});

test("collapses soreness phrasing with filler words", () => {
  assert.equal(normalizeInjuryLabel("my lower back feels sore"), "Lower back soreness");
});

test("leaves clean location-only labels untouched", () => {
  assert.equal(normalizeInjuryLabel("Left hamstring"), "Left hamstring");
});

test("returns empty string for blank input", () => {
  assert.equal(normalizeInjuryLabel(""), "");
  assert.equal(normalizeInjuryLabel(null), "");
  assert.equal(normalizeInjuryLabel(undefined), "");
});

test("falls back to the condition alone when no location remains", () => {
  assert.equal(normalizeInjuryLabel("it is bruised"), "Bruise");
});

test("preserves numbers and acronyms in the location", () => {
  assert.equal(normalizeInjuryLabel("L5-S1 stiffness"), "L5-S1 stiffness");
  assert.equal(normalizeInjuryLabel("ACL grade 2 tear"), "ACL grade 2 tear");
});

test("normalizes the casing of spinal levels and known acronyms", () => {
  assert.equal(normalizeInjuryLabel("l5-s1 stiffness"), "L5-S1 stiffness");
  assert.equal(normalizeInjuryLabel("acl tear"), "ACL tear");
  assert.equal(normalizeInjuryLabel("left ACL tear"), "Left ACL tear");
});

test("keeps single spinal levels and injury grades", () => {
  assert.equal(normalizeInjuryLabel("C5 nerve pain"), "C5 nerve pain");
  assert.equal(normalizeInjuryLabel("T4 stiffness"), "T4 stiffness");
  assert.equal(normalizeInjuryLabel("grade 1 hamstring strain"), "Grade 1 hamstring strain");
});

// "IT" (iliotibial) is the one acronym that collides with a filler word, so the
// uppercase form must survive where the lowercase pronoun is still stripped.
test("keeps an uppercase IT band but still strips the pronoun 'it'", () => {
  assert.equal(normalizeInjuryLabel("IT band pain"), "IT band pain");
  assert.equal(normalizeInjuryLabel("it is bruised"), "Bruise");
});

test("does not preserve shouty input as an acronym", () => {
  assert.equal(normalizeInjuryLabel("LEFT SHOULDER IS BRUISED"), "Left shoulder bruise");
});

test("strips duplicated condition debris from messy parser strings", () => {
  assert.equal(
    normalizeInjuryLabel("Left shoulder contusion (bruise, left)"),
    "Left shoulder bruise",
  );
});

test("normalizes a leading condition with trailing location", () => {
  assert.equal(normalizeInjuryLabel("bruise, left shoulder"), "Left shoulder bruise");
});
