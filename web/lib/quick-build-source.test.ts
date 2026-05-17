import test from "node:test";
import assert from "node:assert/strict";

import { dismissBanner, isBannerDismissed } from "@/lib/quick-build-source";

class MemoryStorage {
  private store = new Map<string, string>();
  get length(): number { return this.store.size; }
  key(index: number): string | null { return Array.from(this.store.keys())[index] ?? null; }
  getItem(key: string): string | null { return this.store.has(key) ? this.store.get(key)! : null; }
  setItem(key: string, value: string): void { this.store.set(key, String(value)); }
  removeItem(key: string): void { this.store.delete(key); }
  clear(): void { this.store.clear(); }
}

type WindowLike = { localStorage: MemoryStorage };

function installWindow(): WindowLike {
  const win: WindowLike = { localStorage: new MemoryStorage() };
  (globalThis as unknown as { window: WindowLike }).window = win;
  return win;
}

function clearWindow(): void {
  delete (globalThis as unknown as { window?: WindowLike }).window;
}

test("dismissBanner / isBannerDismissed round-trip", () => {
  installWindow();
  try {
    assert.equal(isBannerDismissed("plan-x"), false);
    dismissBanner("plan-x");
    assert.equal(isBannerDismissed("plan-x"), true);
    assert.equal(isBannerDismissed("plan-y"), false);
  } finally {
    clearWindow();
  }
});

test("dismissBanner does not duplicate the same id", () => {
  const win = installWindow();
  try {
    dismissBanner("plan-1");
    dismissBanner("plan-1");
    const stored = JSON.parse(win.localStorage.getItem("unlxck:quick-build-banner-dismissed") ?? "[]") as string[];
    assert.equal(stored.length, 1);
  } finally {
    clearWindow();
  }
});

test("dismissBanner FIFO-trims past the cap of 50", () => {
  const win = installWindow();
  try {
    for (let i = 0; i < 60; i += 1) {
      dismissBanner(`plan-${i}`);
    }
    const stored = JSON.parse(win.localStorage.getItem("unlxck:quick-build-banner-dismissed") ?? "[]") as string[];
    assert.equal(stored.length, 50);
    assert.equal(stored[0], "plan-10");
    assert.equal(stored[stored.length - 1], "plan-59");
    assert.equal(isBannerDismissed("plan-0"), false);
    assert.equal(isBannerDismissed("plan-59"), true);
  } finally {
    clearWindow();
  }
});

test("functions are safe when window is undefined", () => {
  clearWindow();
  assert.equal(isBannerDismissed("plan-1"), false);
  assert.doesNotThrow(() => dismissBanner("plan-1"));
});
