import test from "node:test";
import assert from "node:assert/strict";

import { NAV_TOGGLE_CONDENSE_THRESHOLD, isNavToggleCondensed } from "./nav-toggle-scroll";

test("the toggle is full size at and below the top threshold", () => {
  assert.equal(isNavToggleCondensed(0), false);
  assert.equal(isNavToggleCondensed(NAV_TOGGLE_CONDENSE_THRESHOLD), false);
});

test("the toggle condenses once scrolled past the top threshold", () => {
  assert.equal(isNavToggleCondensed(NAV_TOGGLE_CONDENSE_THRESHOLD + 1), true);
  assert.equal(isNavToggleCondensed(1000), true);
});
