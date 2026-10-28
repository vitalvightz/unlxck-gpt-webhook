import assert from "node:assert/strict";
import test from "node:test";
import "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";

import { AutoHeight } from "@/components/today/auto-height";

function stubMotion(reduced: boolean) {
  const matchMedia = window.matchMedia;
  const animate = (window.HTMLElement.prototype as { animate?: unknown }).animate;
  const calls: Keyframe[][] = [];
  Object.defineProperty(window, "matchMedia", { configurable: true, value: (query: string) => ({
    matches: reduced && query.includes("reduce"), media: query, onchange: null,
    addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent: () => false,
  }) });
  (window.HTMLElement.prototype as { animate?: unknown }).animate = (keyframes: Keyframe[]) => {
    calls.push(keyframes);
    return { cancel() {} };
  };
  return {
    calls,
    restore() {
      Object.defineProperty(window, "matchMedia", { configurable: true, value: matchMedia });
      (window.HTMLElement.prototype as { animate?: unknown }).animate = animate;
    },
  };
}

async function swap(reduced: boolean) {
  const motion = stubMotion(reduced);
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<AutoHeight swapKey="filters" swapMotion="forward"><p>Filters</p></AutoHeight>));
    await act(async () => root.render(<AutoHeight swapKey="equipment" swapMotion="forward"><p>Equipment</p></AutoHeight>));
    return motion.calls;
  } finally {
    act(() => root.unmount());
    container.remove();
    motion.restore();
  }
}

test("new content slides in when its key changes", async () => {
  const calls = await swap(false);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0].transform, "translateX(24px)");
});

test("with reduced motion new content simply appears, with no fade", async () => {
  assert.deepEqual(await swap(true), []);
});
