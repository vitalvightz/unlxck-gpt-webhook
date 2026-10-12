import assert from "node:assert/strict";
import test from "node:test";
import { getExerciseAdditions } from "./api";

test("superseded exercise searches preserve cancellation without a network-error log", async () => {
  const oldFetch = globalThis.fetch;
  const oldError = console.error;
  const errors: unknown[] = [];
  console.error = (...args) => { errors.push(args); };
  globalThis.fetch = ((_url, init) => new Promise((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new DOMException("Request aborted", "AbortError")), { once: true });
  })) as typeof fetch;
  try {
    const controller = new AbortController();
    const pending = getExerciseAdditions("token", "plan", { date: "2026-10-12", sessionId: "session", q: "run" }, controller.signal);
    controller.abort();
    await assert.rejects(pending, { name: "AbortError" });
    assert.deepEqual(errors, []);
  } finally {
    globalThis.fetch = oldFetch;
    console.error = oldError;
  }
});
