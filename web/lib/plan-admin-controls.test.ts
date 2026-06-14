import assert from "node:assert/strict";
import test from "node:test";

import { canUseAdminPlanControls, isAdminRole } from "./plan-admin-controls";

// --- admin-output-dependent controls (approve / reject / archive / admin review)

test("admin with admin_outputs sees admin-output-dependent controls", () => {
  assert.equal(canUseAdminPlanControls("admin", true), true);
});

test("admin without admin_outputs cannot see admin-output-dependent controls", () => {
  assert.equal(canUseAdminPlanControls("admin", false), false);
});

test("athlete cannot see approve/reject/archive/admin review controls", () => {
  assert.equal(canUseAdminPlanControls("athlete", true), false);
  assert.equal(canUseAdminPlanControls("athlete", false), false);
});

test("non-admin roles are gated off admin-output-dependent controls", () => {
  assert.equal(canUseAdminPlanControls("coach", true), false);
  assert.equal(canUseAdminPlanControls("gym_owner", true), false);
  assert.equal(canUseAdminPlanControls(null, true), false);
  assert.equal(canUseAdminPlanControls(undefined, true), false);
});

// --- general admin-only controls (permanent delete / view athlete profile)

test("admin without admin_outputs can still use general admin actions", () => {
  // Permanent delete and View athlete profile depend on role only.
  assert.equal(isAdminRole("admin"), true);
});

test("athlete cannot see any admin-only controls", () => {
  assert.equal(isAdminRole("athlete"), false);
  assert.equal(canUseAdminPlanControls("athlete", true), false);
  assert.equal(canUseAdminPlanControls("athlete", false), false);
});

test("non-admin roles are gated off general admin actions", () => {
  assert.equal(isAdminRole("coach"), false);
  assert.equal(isAdminRole("gym_owner"), false);
  assert.equal(isAdminRole(null), false);
  assert.equal(isAdminRole(undefined), false);
});
