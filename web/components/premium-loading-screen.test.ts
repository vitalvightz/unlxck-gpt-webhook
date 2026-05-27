import test from "node:test";
import assert from "node:assert/strict";

import { PHASE_CONTENT } from "./premium-loading-screen";

test("already-generated phase renders duplicate-prevention copy, not failure copy", () => {
  const content = PHASE_CONTENT.already_generated;
  assert.equal(content.eyebrow, "Plan already exists");
  assert.equal(content.title, "This intake already has a generated plan.");
  assert.equal(content.copy, "Open the existing plan or refine the intake to create a new version.");
  assert.equal(content.chip, "Already generated");
  assert.equal(content.buildState, "Existing plan");
  assert.equal(content.reassurance, "No new duplicate was created.");
  assert.notEqual(content.title, PHASE_CONTENT.failed.title);
});
