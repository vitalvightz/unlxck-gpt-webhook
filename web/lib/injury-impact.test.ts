import test from "node:test";
import assert from "node:assert/strict";
import { readInjuryImpact, writeInjuryImpact } from "./injury-impact.ts";

test("impact round-trips without dropping safety flags or athlete notes", () => {
  const original = "Worse when punching [red_flags:none]";
  const tagged = writeInjuryImpact(original, "cant_train");
  assert.equal(readInjuryImpact(tagged)?.label, "Can’t train normally");
  const updated = writeInjuryImpact(tagged, "limiting");
  assert.equal(readInjuryImpact(updated)?.flagSeverity, "moderate");
  assert.equal(writeInjuryImpact(updated, ""), original);
  assert.equal(updated.match(/training_impact/g)?.length, 1);
});

test("legacy severity is never presented as an athlete's functional answer", () => {
  assert.equal(readInjuryImpact("moderate shoulder strain"), undefined);
  assert.equal(readInjuryImpact("[training_impact:unknown]"), undefined);
});
