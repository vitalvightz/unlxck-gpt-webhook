import assert from "node:assert/strict";
import test from "node:test";

import { canUseAdminPlanControls } from "./plan-admin-controls";

test("admin with admin_outputs sees admin plan controls", () => {
  assert.equal(canUseAdminPlanControls("admin", true), true);
});

test("athlete never sees admin plan controls, even if admin_outputs are present", () => {
  assert.equal(canUseAdminPlanControls("athlete", true), false);
  assert.equal(canUseAdminPlanControls("athlete", false), false);
});

test("non-admin roles are gated off admin plan controls", () => {
  assert.equal(canUseAdminPlanControls("coach", true), false);
  assert.equal(canUseAdminPlanControls("gym_owner", true), false);
  assert.equal(canUseAdminPlanControls(null, true), false);
  assert.equal(canUseAdminPlanControls(undefined, true), false);
});

test("admin without admin_outputs has no admin controls to show", () => {
  assert.equal(canUseAdminPlanControls("admin", false), false);
});
