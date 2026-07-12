import test from "node:test";
import assert from "node:assert/strict";

import { isOpenOngoingPlan } from "./plan-format";

test("identifies only plans without a fight date as open ongoing plans", () => {
  assert.equal(isOpenOngoingPlan(null), true);
  assert.equal(isOpenOngoingPlan("   "), true);
  assert.equal(isOpenOngoingPlan("2026-07-18"), false);
});
