import assert from "node:assert/strict";
import test from "node:test";

import { shouldShowAdminPanelLink } from "./admin-nav-visibility";

test("shows Admin panel link for admin role", () => {
  assert.equal(shouldShowAdminPanelLink("admin"), true);
});

test("shows Admin panel link on admin route while role is missing", () => {
  assert.equal(shouldShowAdminPanelLink(null, true), true);
  assert.equal(shouldShowAdminPanelLink(undefined, true), true);
});

test("hides Admin panel link for athlete outside admin route", () => {
  assert.equal(shouldShowAdminPanelLink("athlete", false), false);
});

test("hides Admin panel link when role is missing", () => {
  assert.equal(shouldShowAdminPanelLink(null, false), false);
  assert.equal(shouldShowAdminPanelLink(undefined, false), false);
});
