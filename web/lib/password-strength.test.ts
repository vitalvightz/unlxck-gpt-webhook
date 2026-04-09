import assert from "node:assert/strict";
import test from "node:test";

import { evaluatePasswordStrength } from "./password-strength.ts";

test("rejects passwords shorter than eight characters", () => {
  const result = evaluatePasswordStrength("short7");
  assert.equal(result.tone, "red");
  assert.equal(result.isAcceptable, false);
  assert.equal(result.minLengthMet, false);
});

test("rejects passwords that match the supplied name or email context", () => {
  const result = evaluatePasswordStrength("AriMensah2026", {
    fullName: "Ari Mensah",
    email: "ari@example.com",
  });
  assert.equal(result.isAcceptable, false);
});

test("accepts amber-rated passwords without requiring symbols", () => {
  const result = evaluatePasswordStrength("trainingblock27");
  assert.notEqual(result.tone, "red");
  assert.equal(result.isAcceptable, true);
});

test("accepts strong passphrases without symbols", () => {
  const result = evaluatePasswordStrength("correct horse battery staple");
  assert.equal(result.tone, "green");
  assert.equal(result.isAcceptable, true);
});
