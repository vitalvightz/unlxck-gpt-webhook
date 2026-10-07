import test from "node:test";
import assert from "node:assert/strict";
import "../components/test-dom";
import { lockOverlayScroll } from "./overlay-scroll-lock";

test("nested overlays freeze a scrolled document and restore it only after the last release", () => {
  const originalScroll = window.scrollTo;
  const calls: number[][] = [];
  window.scrollTo = ((x: number, y: number) => { calls.push([x, y]); }) as typeof window.scrollTo;
  Object.defineProperty(window, "scrollY", { value: 640, configurable: true });
  document.body.style.position = "relative";
  document.body.style.overflow = "auto";
  try {
    const first = lockOverlayScroll();
    const second = lockOverlayScroll();
    assert.equal(document.body.style.top, "-640px");
    assert.equal(document.body.style.position, "fixed");
    first();
    first(); // Cleanup is idempotent.
    assert.equal(document.body.style.position, "fixed");
    assert.equal(calls.length, 0);
    second();
    assert.equal(document.body.style.position, "relative");
    assert.equal(document.body.style.overflow, "auto");
    assert.equal(document.body.style.top, "");
    assert.deepEqual(calls, [[0, 640]]);
  } finally {
    window.scrollTo = originalScroll;
    Object.defineProperty(window, "scrollY", { value: 0, configurable: true });
    document.body.style.cssText = "";
  }
});
