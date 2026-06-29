import test from "node:test";
import assert from "node:assert/strict";

import { emptyPlanRequest } from "@/lib/onboarding";
import {
  clearPendingGenerationPayload,
  readPendingGenerationPayload,
  writePendingGenerationPayload,
} from "@/lib/generation-pending-payload";

const PENDING_GENERATION_PAYLOAD_KEY = "unlxck:pending-generation-payload:v1";

class MemoryStorage implements Storage {
  private store = new Map<string, string>();

  get length() {
    return this.store.size;
  }

  clear() {
    this.store.clear();
  }

  getItem(key: string) {
    return this.store.get(key) ?? null;
  }

  key(index: number) {
    return Array.from(this.store.keys())[index] ?? null;
  }

  removeItem(key: string) {
    this.store.delete(key);
  }

  setItem(key: string, value: string) {
    this.store.set(key, value);
  }
}

function installSessionStorage(storage = new MemoryStorage()) {
  Object.defineProperty(globalThis, "window", {
    value: { sessionStorage: storage },
    configurable: true,
  });

  return storage;
}

test("readPendingGenerationPayload rejects non-numeric createdAtMs and clears storage", () => {
  const storage = installSessionStorage();
  const payload = emptyPlanRequest("Athlete");

  storage.setItem(
    PENDING_GENERATION_PAYLOAD_KEY,
    JSON.stringify({
      version: 1,
      payload,
      payloadHash: "test",
      planSource: "self_serve",
      createdAtMs: "not-a-number",
    }),
  );

  assert.equal(readPendingGenerationPayload(), null);
  assert.equal(storage.getItem(PENDING_GENERATION_PAYLOAD_KEY), null);
});

test("readPendingGenerationPayload rejects NaN-like createdAtMs and clears storage", () => {
  const storage = installSessionStorage();
  const payload = emptyPlanRequest("Athlete");

  storage.setItem(
    PENDING_GENERATION_PAYLOAD_KEY,
    JSON.stringify({
      version: 1,
      payload,
      payloadHash: "test",
      planSource: "self_serve",
      createdAtMs: null,
    }),
  );

  assert.equal(readPendingGenerationPayload(), null);
  assert.equal(storage.getItem(PENDING_GENERATION_PAYLOAD_KEY), null);
});

test("readPendingGenerationPayload rejects expired payload and clears storage", () => {
  const storage = installSessionStorage();
  const payload = emptyPlanRequest("Athlete");

  storage.setItem(
    PENDING_GENERATION_PAYLOAD_KEY,
    JSON.stringify({
      version: 1,
      payload,
      payloadHash: "test",
      planSource: "self_serve",
      createdAtMs: Date.now() - 6 * 60 * 1000,
    }),
  );

  assert.equal(readPendingGenerationPayload(), null);
  assert.equal(storage.getItem(PENDING_GENERATION_PAYLOAD_KEY), null);
});

test("readPendingGenerationPayload reads a valid pending payload", () => {
  const storage = installSessionStorage();
  const payload = emptyPlanRequest("Athlete");

  assert.equal(writePendingGenerationPayload(payload, "self_serve"), true);

  const pending = readPendingGenerationPayload();

  assert.ok(pending);
  assert.deepEqual(pending.payload, payload);
  assert.equal(pending.planSource, "self_serve");
  assert.equal(typeof pending.createdAtMs, "number");

  clearPendingGenerationPayload();
  assert.equal(storage.getItem(PENDING_GENERATION_PAYLOAD_KEY), null);
});
