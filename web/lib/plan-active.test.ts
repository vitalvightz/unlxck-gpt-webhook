import test from "node:test";
import assert from "node:assert/strict";

import { canSetActivePlan, isCompletedFightCamp } from "./plan-active";

test("only the server-derived eligible state permits activation", () => {
  assert.equal(canSetActivePlan("eligible"), true);
  assert.equal(canSetActivePlan("fight_date_passed"), false);
  assert.equal(canSetActivePlan("status_ineligible"), false);
  assert.equal(canSetActivePlan(undefined), false);
});

test("completed fight camps are identified from the server-derived state", () => {
  assert.equal(isCompletedFightCamp("fight_date_passed"), true);
  assert.equal(isCompletedFightCamp("eligible"), false);
  assert.equal(isCompletedFightCamp("status_ineligible"), false);
});
