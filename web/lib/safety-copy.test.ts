import test from "node:test";
import assert from "node:assert/strict";

import {
  INJURY_INTAKE_SAFETY,
  PLAN_SAFETY_NOTE,
  SAFETY_DISCLAIMER_SHORT,
  SAFETY_DISCLAIMER_TIGHT,
  SAFETY_NOT_MEDICAL_ADVICE,
  SAFETY_RED_FLAGS,
  TODAY_RED_FLAG_SAFETY,
  WEIGHT_CUT_SAFETY,
} from "./safety-copy";

const ALL_COPY: ReadonlyArray<[string, string]> = [
  ["SAFETY_NOT_MEDICAL_ADVICE", SAFETY_NOT_MEDICAL_ADVICE],
  ["SAFETY_DISCLAIMER_SHORT", SAFETY_DISCLAIMER_SHORT],
  ["SAFETY_DISCLAIMER_TIGHT", SAFETY_DISCLAIMER_TIGHT],
  ["INJURY_INTAKE_SAFETY", INJURY_INTAKE_SAFETY],
  ["TODAY_RED_FLAG_SAFETY", TODAY_RED_FLAG_SAFETY],
  ["PLAN_SAFETY_NOTE", PLAN_SAFETY_NOTE],
  ["WEIGHT_CUT_SAFETY", WEIGHT_CUT_SAFETY],
  ...SAFETY_RED_FLAGS.map((flag, i): [string, string] => [`SAFETY_RED_FLAGS[${i}]`, flag]),
];

test("core disclaimers state Unlxck is not medical advice", () => {
  assert.match(SAFETY_NOT_MEDICAL_ADVICE, /not medical advice/i);
  assert.match(SAFETY_DISCLAIMER_SHORT, /not medical advice/i);
  assert.match(SAFETY_DISCLAIMER_TIGHT, /not medical advice/i);
  assert.match(INJURY_INTAKE_SAFETY, /does not diagnose|medical clearance/i);
  assert.match(WEIGHT_CUT_SAFETY, /not medical advice|qualified professional/i);
});

test("injury and weight-cut copy name concrete red-flag actions", () => {
  assert.match(INJURY_INTAKE_SAFETY, /seek medical help/i);
  assert.match(TODAY_RED_FLAG_SAFETY, /seek medical help/i);
  assert.match(WEIGHT_CUT_SAFETY, /dehydration/i);
});

test("red-flag list covers neurological, chest, and dehydration symptoms", () => {
  const joined = SAFETY_RED_FLAGS.join(" ").toLowerCase();
  assert.ok(joined.includes("neurological"));
  assert.ok(joined.includes("chest pain"));
  assert.ok(joined.includes("dehydration"));
  assert.ok(joined.includes("swelling"));
});

test("plan copy frames training as input-driven, not medical clearance", () => {
  // Must NOT promise clearance; must explicitly disclaim it.
  assert.match(PLAN_SAFETY_NOTE, /current inputs/i);
  assert.match(PLAN_SAFETY_NOTE, /not medical clearance/i);
});

test("no copy makes an unsafe positive medical claim", () => {
  // Banned: reassurance/clearance phrasing that reads as medical advice. The
  // disclaimers may say "not medical clearance" (negated), which is allowed,
  // so we only ban positive claims.
  const bannedPatterns: ReadonlyArray<RegExp> = [
    /\bsafe to train\b/i,
    /\binjury cleared\b/i,
    /\byou are cleared\b/i,
    /\bmedically cleared to\b/i,
    /\bguarantee(d|s)?\b/i,
  ];
  for (const [name, copy] of ALL_COPY) {
    for (const pattern of bannedPatterns) {
      assert.ok(
        !pattern.test(copy),
        `${name} contains unsafe wording matching ${pattern}: "${copy}"`,
      );
    }
  }
});

test("tight disclaimer uses exact mobile copy", () => {
  assert.equal(
    SAFETY_DISCLAIMER_TIGHT,
    "Unlxck is not medical advice. Stop if symptoms worsen, seek help for red flags, and follow your coach or clinician.",
  );
});
