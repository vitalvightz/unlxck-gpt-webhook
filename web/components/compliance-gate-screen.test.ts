import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const SOURCE = readFileSync(new URL("./compliance-gate-screen.tsx", import.meta.url), "utf8");

test("profile verification uses the concise approved copy and legal links", () => {
  for (const text of [
    "Athlete Profile Verification",
    "Set your baseline to unlock personalized camp programming and safety protocols.",
    "Must be 18+ for full weight-cut protocols.",
    "I agree to the",
    "Allow UNLXCK to process health and recovery metrics to adapt my camp.",
  ]) {
    assert.ok(SOURCE.includes(text), text);
  }
  assert.ok(SOURCE.includes('href="/terms"'));
  assert.ok(SOURCE.includes('href="/privacy"'));
  assert.ok(!SOURCE.includes("Under-18s get extra privacy and safety protections"));
  assert.ok(!SOURCE.includes("healthConsentHelp"));
  assert.ok(!SOURCE.includes("declineNote"));
});

test("both choices start unchecked and block continuation while incomplete", () => {
  assert.match(SOURCE, /\[acceptedTerms, setAcceptedTerms\] = useState\(false\)/);
  assert.match(SOURCE, /\[healthDataConsent, setHealthDataConsent\] = useState\(false\)/);
  assert.ok(SOURCE.includes("(!needsTerms || acceptedTerms)"));
  assert.ok(SOURCE.includes("(!needsHealthConsent || healthDataConsent)"));
  assert.ok(SOURCE.includes("disabled={!canContinue}"));
  assert.ok(SOURCE.includes("if (needsHealthConsent && !healthDataConsent)"));
});
