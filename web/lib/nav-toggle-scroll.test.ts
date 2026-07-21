import test from "node:test";
import assert from "node:assert/strict";

import {
  NAV_TOGGLE_INITIAL_STATE,
  NAV_TOGGLE_HIDE_THRESHOLD,
  NAV_TOGGLE_TOP_THRESHOLD,
  nextNavToggleScrollState,
  type NavToggleScrollState,
} from "./nav-toggle-scroll";

const shown: NavToggleScrollState = { hidden: false, condensed: false };
const hidden: NavToggleScrollState = { hidden: true, condensed: true };

test("stays fully shown and un-condensed at the top of the page", () => {
  assert.deepEqual(nextNavToggleScrollState(shown, 0, 0), { hidden: false, condensed: false });
  assert.deepEqual(
    nextNavToggleScrollState(shown, NAV_TOGGLE_TOP_THRESHOLD, 0),
    { hidden: false, condensed: false },
  );
});

test("condenses once scrolled past the top threshold, independent of hide state", () => {
  assert.equal(nextNavToggleScrollState(shown, NAV_TOGGLE_TOP_THRESHOLD + 1, 0).condensed, true);
  // Small nudge past the top condenses but does not yet hide.
  assert.deepEqual(
    nextNavToggleScrollState(shown, NAV_TOGGLE_TOP_THRESHOLD + 1, 0),
    { hidden: false, condensed: true },
  );
});

test("hides when scrolling down well past the top", () => {
  const y = NAV_TOGGLE_HIDE_THRESHOLD + 40;
  assert.equal(nextNavToggleScrollState(shown, y, y - 20).hidden, true);
});

test("does not hide while scrolling down but still within the hide threshold", () => {
  // Moving down between the top and hide thresholds: condensed, not hidden.
  const y = NAV_TOGGLE_HIDE_THRESHOLD - 10;
  const next = nextNavToggleScrollState(shown, y, y - 15);
  assert.equal(next.hidden, false);
  assert.equal(next.condensed, true);
});

test("returns immediately on any scroll up, even while deep in the page", () => {
  const next = nextNavToggleScrollState(hidden, 300, 360);
  assert.equal(next.hidden, false);
  // Still scrolled, so it stays condensed.
  assert.equal(next.condensed, true);
});

test("stays hidden across a no-movement sample while scrolled down", () => {
  const y = NAV_TOGGLE_HIDE_THRESHOLD + 100;
  const next = nextNavToggleScrollState(hidden, y, y);
  assert.equal(next.hidden, true);
});

test("scrolling back to the very top overrides a hidden state", () => {
  const next = nextNavToggleScrollState(hidden, 0, 200);
  assert.deepEqual(next, { hidden: false, condensed: false });
});

test("initial state is shown and un-condensed", () => {
  assert.deepEqual(NAV_TOGGLE_INITIAL_STATE, { hidden: false, condensed: false });
});
