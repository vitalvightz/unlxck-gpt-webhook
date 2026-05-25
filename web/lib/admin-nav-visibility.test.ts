import assert from "node:assert/strict";
import test from "node:test";

import { shouldShowAdminPanelLink } from "./admin-nav-visibility";

test("shows Admin panel link for admin role", () => {
  assert.equal(shouldShowAdminPanelLink("admin"), true);
});

test("hides Admin panel link for athlete role", () => {
  assert.equal(shouldShowAdminPanelLink("athlete"), false);
});

test("hides Admin panel link when role is missing", () => {
  assert.equal(shouldShowAdminPanelLink(null), false);
  assert.equal(shouldShowAdminPanelLink(undefined), false);
});
