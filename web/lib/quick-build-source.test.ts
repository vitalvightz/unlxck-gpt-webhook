import test from "node:test";
import assert from "node:assert/strict";

import {
  consumePendingQuickBuildForPlan,
  dismissBanner,
  isBannerDismissed,
  isQuickBuildPlan,
  markPendingQuickBuild,
} from "@/lib/quick-build-source";

class MemoryStorage {
  private store = new Map<string, string>();
  get length(): number { return this.store.size; }
  key(index: number): string | null { return Array.from(this.store.keys())[index] ?? null; }
  getItem(key: string): string | null { return this.store.has(key) ? this.store.get(key)! : null; }
  setItem(key: string, value: string): void { this.store.set(key, String(value)); }
  removeItem(key: string): void { this.store.delete(key); }
  clear(): void { this.store.clear(); }
}

type WindowLike = { sessionStorage: MemoryStorage; localStorage: MemoryStorage };

function installWindow(): WindowLike {
  const win: WindowLike = { sessionStorage: new MemoryStorage(), localStorage: new MemoryStorage() };
  (globalThis as unknown as { window: WindowLike }).window = win;
  return win;
}

function clearWindow(): void {
  delete (globalThis as unknown as { window?: WindowLike }).window;
}

test("markPendingQuickBuild + consumePendingQuickBuildForPlan adds the plan id", () => {
  const win = installWindow();
  try {
    markPendingQuickBuild();
    assert.equal(win.sessionStorage.getItem("unlxck:pending-plan-source"), "quick_build");
    consumePendingQuickBuildForPlan("plan-1");
    assert.equal(isQuickBuildPlan("plan-1"), true);
    assert.equal(win.sessionStorage.getItem("unlxck:pending-plan-source"), null);
  } finally {
    clearWindow();
  }
});

test("consumePendingQuickBuildForPlan is a no-op without the pending mark", () => {
  installWindow();
  try {
    consumePendingQuickBuildForPlan("plan-1");
    assert.equal(isQuickBuildPlan("plan-1"), false);
  } finally {
    clearWindow();
  }
});

test("isQuickBuildPlan only returns true for marked ids", () => {
  installWindow();
  try {
    markPendingQuickBuild();
    consumePendingQuickBuildForPlan("plan-a");
    assert.equal(isQuickBuildPlan("plan-a"), true);
    assert.equal(isQuickBuildPlan("plan-b"), false);
  } finally {
    clearWindow();
  }
});

test("plan id list evicts FIFO once the cap is reached", () => {
  const win = installWindow();
  try {
    for (let i = 0; i < 30; i += 1) {
      markPendingQuickBuild();
      consumePendingQuickBuildForPlan(`plan-${i}`);
    }
    const stored = JSON.parse(win.localStorage.getItem("unlxck:quick-build-plan-ids") ?? "[]") as string[];
    assert.equal(stored.length, 25);
    assert.equal(stored[0], "plan-5");
    assert.equal(stored[stored.length - 1], "plan-29");
    assert.equal(isQuickBuildPlan("plan-0"), false);
    assert.equal(isQuickBuildPlan("plan-29"), true);
  } finally {
    clearWindow();
  }
});

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

test("all functions are safe when window is undefined", () => {
  clearWindow();
  assert.doesNotThrow(() => markPendingQuickBuild());
  assert.doesNotThrow(() => consumePendingQuickBuildForPlan("plan-1"));
  assert.equal(isQuickBuildPlan("plan-1"), false);
  assert.equal(isBannerDismissed("plan-1"), false);
  assert.doesNotThrow(() => dismissBanner("plan-1"));
});

test("consumePendingQuickBuildForPlan does not double-add the same plan id", () => {
  const win = installWindow();
  try {
    markPendingQuickBuild();
    consumePendingQuickBuildForPlan("plan-1");
    markPendingQuickBuild();
    consumePendingQuickBuildForPlan("plan-1");
    const stored = JSON.parse(win.localStorage.getItem("unlxck:quick-build-plan-ids") ?? "[]") as string[];
    assert.equal(stored.length, 1);
  } finally {
    clearWindow();
  }
});
