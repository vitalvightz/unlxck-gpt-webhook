import assert from "node:assert/strict";
import test, { afterEach, beforeEach } from "node:test";

import { getPlan } from "./api.ts";

const PLAN_ID = "11111111-1111-1111-1111-111111111111";
const realFetch = globalThis.fetch;
const realConsole = { info: console.info, warn: console.warn, error: console.error };

beforeEach(() => {
  console.info = () => {};
  console.warn = () => {};
  console.error = () => {};
});

afterEach(() => {
  globalThis.fetch = realFetch;
  Object.assign(console, realConsole);
});

function abortError(): DOMException {
  return new DOMException("The operation was aborted.", "AbortError");
}

test("aborting getPlan cancels the request and does not retry it", async () => {
  const signals: AbortSignal[] = [];
  globalThis.fetch = ((_url: string, init?: RequestInit) => {
    const signal = init?.signal as AbortSignal;
    signals.push(signal);
    // Like a real slow request: settles only when its signal aborts.
    return new Promise<Response>((_resolve, reject) => {
      signal.addEventListener("abort", () => reject(abortError()));
    });
  }) as typeof fetch;

  const controller = new AbortController();
  const request = getPlan("token", PLAN_ID, { signal: controller.signal });
  await Promise.resolve();
  controller.abort();

  await assert.rejects(request);
  // An abort surfaces as the retryable network error, but it must not be retried.
  assert.equal(signals.length, 1);
  assert.equal(signals[0].aborted, true);
});

test("aborting getPlan while its body downloads cancels the download", async () => {
  const signals: AbortSignal[] = [];
  globalThis.fetch = ((_url: string, init?: RequestInit) => {
    const signal = init?.signal as AbortSignal;
    signals.push(signal);
    // Headers arrive at once; the body streams until the signal aborts.
    const body = new ReadableStream<Uint8Array>({
      start(stream) {
        stream.enqueue(new TextEncoder().encode('{"plan_id":'));
        signal.addEventListener("abort", () => stream.error(abortError()));
      },
    });
    return Promise.resolve(
      new Response(body, { status: 200, headers: { "Content-Type": "application/json" } }),
    );
  }) as typeof fetch;

  const controller = new AbortController();
  const request = getPlan("token", PLAN_ID, { signal: controller.signal });
  await new Promise((resolve) => setTimeout(resolve, 10));
  controller.abort();

  await assert.rejects(request);
  assert.equal(signals.length, 1);
  assert.equal(signals[0].aborted, true);
});
