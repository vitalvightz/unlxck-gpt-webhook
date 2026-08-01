import assert from "node:assert/strict";
import test from "node:test";

import { formatInjuryDetail, normalizeInjuryLabel } from "./injury-display.ts";

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

// formatInjuryDetail ---------------------------------------------------------

test("strips the planner's taxonomy tokens out of a guided-intake description", () => {
  assert.equal(
    formatInjuryDetail("Right shoulder: blister. surface injury. surface injury:blister", {
      bodyArea: "Right shoulder",
    }),
    "blister",
  );
  // The raw stored form, before the backend humanizes the underscores away.
  assert.equal(
    formatInjuryDetail("Right shoulder: blister. surface_injury. surface_injury:blister", {
      bodyArea: "Right shoulder",
    }),
    "blister",
  );
  // Casing is not guaranteed on a stored enum.
  assert.equal(
    formatInjuryDetail("Surface_Injury:Blister. Surface Injury", { bodyArea: "Right shoulder" }),
    "",
  );
});

// A colon is ordinary punctuation in athlete prose. Only a recognised taxonomy
// family followed by a single bare token is internal vocabulary — everything
// else is what the athlete typed, and dropping it loses their report.
test("keeps athlete prose that happens to contain a colon", () => {
  assert.equal(formatInjuryDetail("pain:sharp when running"), "pain:sharp when running");
  assert.equal(formatInjuryDetail("worse:after sparring"), "worse:after sparring");
  assert.equal(formatInjuryDetail("bruise. note:knocked it again"), "bruise. note:knocked it again");
  assert.equal(formatInjuryDetail("surface_injury:blister"), "");
});

test("keeps the condition word and the athlete's own detail", () => {
  assert.equal(
    formatInjuryDetail("bruise. worse when sprinting"),
    "bruise. worse when sprinting",
  );
  assert.equal(formatInjuryDetail("blister on left foot"), "blister on left foot");
});

test("drops a body-area segment that only restates the location", () => {
  assert.equal(formatInjuryDetail("Left shoulder", { bodyArea: "Left shoulder" }), "");
  assert.equal(
    formatInjuryDetail("Left shoulder: soreness. this week", { bodyArea: "left shoulder" }),
    "soreness. this week",
  );
});

// The "<body area>: <condition>" prefix an athlete-facing description uses is
// the one colon that must survive — only the space-less `family:specific` pair
// is internal vocabulary.
test("keeps a colon that separates the location from the condition", () => {
  assert.equal(formatInjuryDetail("Left knee: sore after running"), "Left knee: sore after running");
});

test("dedupes repeated segments and tolerates blank input", () => {
  assert.equal(formatInjuryDetail("bruise. Bruise. bruise"), "bruise");
  assert.equal(formatInjuryDetail(""), "");
  assert.equal(formatInjuryDetail(null), "");
  assert.equal(formatInjuryDetail(undefined), "");
});
