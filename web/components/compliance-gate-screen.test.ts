import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const SOURCE = readFileSync(new URL("./compliance-gate-screen.tsx", import.meta.url), "utf8");

test("account completion uses concise copy, shared consent wording and legal links", () => {
  for (const text of [
    "Finish your account",
    "I accept the",
    "consentCopy.signupHealthConsentLabel",
  ]) {
    assert.ok(SOURCE.includes(text), text);
  }
  assert.ok(SOURCE.includes('href="/terms"'));
  assert.ok(SOURCE.includes('href="/privacy"'));
  assert.ok(!SOURCE.includes("Under-18s get extra privacy and safety protections"));
  assert.ok(!SOURCE.includes("Must be 18+ for full weight-cut protocols"));
  assert.ok(!SOURCE.includes("healthConsentHelp"));
  assert.ok(SOURCE.includes("consentCopy.declineNote"));
});

test("health consent starts unchecked but does not block account continuation", () => {
  assert.match(SOURCE, /\[acceptedTerms, setAcceptedTerms\] = useState\(false\)/);
  assert.match(SOURCE, /\[healthDataConsent, setHealthDataConsent\] = useState\(false\)/);
  assert.ok(SOURCE.includes("(!needsTerms || acceptedTerms)"));
  assert.ok(!SOURCE.includes("(!needsHealthConsent || healthDataConsent)"));
  assert.ok(SOURCE.includes("disabled={!canContinue}"));
  assert.ok(!SOURCE.includes("if (needsHealthConsent && !healthDataConsent)"));
});
