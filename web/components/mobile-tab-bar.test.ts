import test from "node:test";
import assert from "node:assert/strict";

import { visualViewportBottomOffset } from "./mobile-tab-bar";

test("the tab bar stays at bottom: 0 while the viewports agree", () => {
  assert.equal(visualViewportBottomOffset(800, { height: 800, offsetTop: 0, scale: 1 }), 0);
  assert.equal(visualViewportBottomOffset(800, null), 0);
});

test("a visible area ending below the fixed layer pulls the bar down to it", () => {
  // The floating-bar glitch: the visual viewport has scrolled 92px past the
  // layout viewport, so a bottom: 0 bar sits 92px above the screen's edge.
  assert.equal(visualViewportBottomOffset(800, { height: 800, offsetTop: 92, scale: 1 }), -92);
});

test("a fixed layer stuck at the keyboard-shrunk height is pulled to the screen edge", () => {
  // iOS home-screen app after the keyboard closes: the visual viewport is the
  // full 932px screen again, but the bar's bottom: 0 still lands at 596px.
  // window.innerHeight reports 932 here, so only the bar's own edge shows it.
  assert.equal(visualViewportBottomOffset(596, { height: 932, offsetTop: 0, scale: 1 }), -336);
});

test("the bar is never lifted, and pinch-zoom is left alone", () => {
  // A keyboard shrinks the visual viewport: the bar must not ride up with it.
  assert.equal(visualViewportBottomOffset(800, { height: 480, offsetTop: 0, scale: 1 }), 0);
  assert.equal(visualViewportBottomOffset(800, { height: 400, offsetTop: 500, scale: 2 }), 0);
});
