import test from "node:test";
import assert from "node:assert/strict";
import "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { CustomSelect } from "./custom-select";
import { lockOverlayScroll } from "@/lib/overlay-scroll-lock";

test("select locks only the mobile sheet and preserves an enclosing overlay lock", () => {
  const originalMatchMedia = window.matchMedia;
  let mobile = true;
  const listeners = new Set<() => void>();
  Object.defineProperty(window, "matchMedia", { configurable: true, value: ((query: string) => ({
    get matches() { return mobile; }, media: query,
    addEventListener: (_: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_: string, listener: () => void) => listeners.delete(listener),
  })) as unknown as typeof window.matchMedia });
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  let releaseParent: (() => void) | undefined;
  try {
    act(() => root.render(<CustomSelect id="test-select" value="" placeholder="Choose" options={[{ label: "Strength", value: "strength" }]} onChange={() => {}} />));
    act(() => container.querySelector("button")!.click());
    assert.equal(document.body.style.position, "fixed");
    // Resizing into the desktop dropdown releases this sheet's lock.
    mobile = false;
    act(() => listeners.forEach((listener) => listener()));
    assert.equal(document.body.style.position, "");
    releaseParent = lockOverlayScroll();
    mobile = true;
    act(() => listeners.forEach((listener) => listener()));
    act(() => root.unmount());
    assert.equal(document.body.style.position, "fixed");
    releaseParent();
    releaseParent = undefined;
    assert.equal(document.body.style.position, "");
  } finally {
    act(() => root.unmount());
    releaseParent?.();
    container.remove();
    Object.defineProperty(window, "matchMedia", { configurable: true, value: originalMatchMedia });
  }
});
