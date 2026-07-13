import test from "node:test";
import assert from "node:assert/strict";

import {
  formatAthletePlanStatus,
  getPlanDisplayName,
  isOpenOngoingPlan,
} from "./plan-format";

test("identifies only plans without a fight date as open ongoing plans", () => {
  assert.equal(isOpenOngoingPlan(null), true);
  assert.equal(isOpenOngoingPlan("   "), true);
  assert.equal(isOpenOngoingPlan("2026-07-18"), false);
});

test("gives open plans a useful deterministic performance-block name", () => {
  assert.equal(
    getPlanDisplayName({ fight_date: "", plan_name: "", technical_style: ["boxing"] }),
    "Boxing performance block",
  );
  assert.equal(
    getPlanDisplayName({ fight_date: null, plan_name: null, technical_style: [] }),
    "Ongoing performance block",
  );
});

test("keeps review workflow vocabulary out of athlete-facing status copy", () => {
  assert.equal(formatAthletePlanStatus("publishable_with_flags"), "Ready to train");
  assert.equal(formatAthletePlanStatus("ready"), "Ready to train");
  assert.equal(formatAthletePlanStatus("held_for_review"), "Awaiting review");
});
