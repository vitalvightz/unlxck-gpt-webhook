import test from "node:test";
import assert from "node:assert/strict";

import { clearGenerationIntent, hasGenerationIntent, markGenerationIntent } from "@/lib/generation-intent";

function installMockSessionStorage(): void {
  const store = new Map<string, string>();
  const sessionStorage = {
    getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
    setItem: (key: string, value: string) => {
      store.set(key, String(value));
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
    clear: () => store.clear(),
  };
  (globalThis as { window?: unknown }).window = { sessionStorage } as unknown;
}

function installThrowingSessionStorage(): void {
  const sessionStorage = {
    getItem: () => {
      throw new Error("storage disabled");
    },
    setItem: () => {
      throw new Error("storage disabled");
    },
    removeItem: () => {
      throw new Error("storage disabled");
    },
    clear: () => {
      throw new Error("storage disabled");
    },
  };
  (globalThis as { window?: unknown }).window = { sessionStorage } as unknown;
}

function removeMockWindow(): void {
  delete (globalThis as { window?: unknown }).window;
}

test("intent defaults to absent and reflects mark/clear", () => {
  installMockSessionStorage();
  try {
    assert.equal(hasGenerationIntent(), false);
    markGenerationIntent();
    assert.equal(hasGenerationIntent(), true);
    clearGenerationIntent();
    assert.equal(hasGenerationIntent(), false);
  } finally {
    removeMockWindow();
  }
});

test("intent survives via in-memory fallback when sessionStorage throws", () => {
  installThrowingSessionStorage();
  try {
    assert.equal(hasGenerationIntent(), false);
    // setItem throws, but the in-memory mirror must still record the intent.
    markGenerationIntent();
    assert.equal(hasGenerationIntent(), true);
    // clear must reset the in-memory mirror even though removeItem throws.
    clearGenerationIntent();
    assert.equal(hasGenerationIntent(), false);
  } finally {
    removeMockWindow();
  }
});

test("intent reads false when there is no window (cold tab restore / SSR)", () => {
  removeMockWindow();
  assert.equal(hasGenerationIntent(), false);
  // Mark/clear must be no-ops rather than throwing without a window.
  markGenerationIntent();
  clearGenerationIntent();
  assert.equal(hasGenerationIntent(), false);
});
