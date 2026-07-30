import assert from "node:assert/strict";
import test, { afterEach, beforeEach } from "node:test";

import {
  clearPasswordRecovery,
  hasPasswordRecoveryFor,
  markPasswordRecovery,
  PASSWORD_RECOVERY_STORAGE_KEY,
  PASSWORD_RECOVERY_TTL_MS,
  readPasswordRecovery,
} from "./password-recovery.ts";

const USER = "00000000-0000-4000-8000-000000000001";
const OTHER_USER = "00000000-0000-4000-8000-000000000002";

type MutableGlobal = { window?: { sessionStorage: Storage } };

function installStorage(): Map<string, string> {
  const store = new Map<string, string>();
  const sessionStorage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
    removeItem: (key: string) => void store.delete(key),
    clear: () => store.clear(),
    key: (index: number) => [...store.keys()][index] ?? null,
    get length() {
      return store.size;
    },
  } as unknown as Storage;
  (globalThis as MutableGlobal).window = { sessionStorage };
  return store;
}

let store: Map<string, string>;

beforeEach(() => {
  store = installStorage();
});

afterEach(() => {
  delete (globalThis as MutableGlobal).window;
});

test("round-trips a marker for the recovering user", () => {
  markPasswordRecovery(USER);
  assert.equal(readPasswordRecovery()?.userId, USER);
  assert.equal(hasPasswordRecoveryFor(USER), true);
});

test("never vouches for a different user", () => {
  // A recovery session for one account must not unlock the form for another.
  markPasswordRecovery(USER);
  assert.equal(hasPasswordRecoveryFor(OTHER_USER), false);
});

test("does not vouch for a missing user id", () => {
  markPasswordRecovery(USER);
  assert.equal(hasPasswordRecoveryFor(null), false);
  assert.equal(hasPasswordRecoveryFor(undefined), false);
  assert.equal(hasPasswordRecoveryFor(""), false);
});

test("expires past the TTL", () => {
  store.set(
    PASSWORD_RECOVERY_STORAGE_KEY,
    JSON.stringify({ userId: USER, at: Date.now() - PASSWORD_RECOVERY_TTL_MS - 1_000 }),
  );
  assert.equal(readPasswordRecovery(), null);
  assert.equal(hasPasswordRecoveryFor(USER), false);
});

test("still honours a marker just inside the TTL", () => {
  store.set(
    PASSWORD_RECOVERY_STORAGE_KEY,
    JSON.stringify({ userId: USER, at: Date.now() - (PASSWORD_RECOVERY_TTL_MS - 5_000) }),
  );
  assert.equal(hasPasswordRecoveryFor(USER), true);
});

test("refuses a future timestamp", () => {
  // Tampered or clock-skewed markers must not extend their own life.
  store.set(
    PASSWORD_RECOVERY_STORAGE_KEY,
    JSON.stringify({ userId: USER, at: Date.now() + 60_000 }),
  );
  assert.equal(readPasswordRecovery(), null);
});

test("refuses malformed or hand-written values", () => {
  for (const raw of [
    "not json",
    "null",
    '"a string"',
    "[]",
    "123",
    JSON.stringify({ userId: USER }),
    JSON.stringify({ at: Date.now() }),
    JSON.stringify({ userId: "", at: Date.now() }),
    JSON.stringify({ userId: USER, at: "recently" }),
    JSON.stringify({ userId: USER, at: Number.NaN }),
    JSON.stringify({ userId: { id: USER }, at: Date.now() }),
  ]) {
    store.set(PASSWORD_RECOVERY_STORAGE_KEY, raw);
    assert.equal(readPasswordRecovery(), null, `expected ${raw} to be refused`);
  }
});

test("clears the marker", () => {
  markPasswordRecovery(USER);
  clearPasswordRecovery();
  assert.equal(readPasswordRecovery(), null);
  assert.equal(store.has(PASSWORD_RECOVERY_STORAGE_KEY), false);
});

test("ignores an empty user id when marking", () => {
  markPasswordRecovery("");
  assert.equal(readPasswordRecovery(), null);
});

test("is safe with no window at all", () => {
  delete (globalThis as MutableGlobal).window;
  assert.doesNotThrow(() => markPasswordRecovery(USER));
  assert.equal(readPasswordRecovery(), null);
  assert.equal(hasPasswordRecoveryFor(USER), false);
  assert.doesNotThrow(() => clearPasswordRecovery());
});

test("is safe when storage access throws", () => {
  // Private mode / blocked storage must degrade, not crash the page.
  (globalThis as MutableGlobal).window = {
    get sessionStorage(): Storage {
      throw new Error("blocked by policy");
    },
  } as unknown as MutableGlobal["window"];

  assert.doesNotThrow(() => markPasswordRecovery(USER));
  assert.equal(readPasswordRecovery(), null);
  assert.doesNotThrow(() => clearPasswordRecovery());
});
