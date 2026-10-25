import test from "node:test";
import assert from "node:assert/strict";
import {
  getAnalyticsPreference,
  setAnalyticsPreference,
  trackProductEvent,
  productEventIdentity,
} from "./api";
import { percent } from "./product-analytics";

test("no consent means no interaction requests; opt-in and withdrawal are account scoped", async () => {
  const original = globalThis.fetch;
  const calls: { path: string; body: unknown }[] = [];
  let enabled = false;
  globalThis.fetch = async (input, init) => {
    const path = String(input);
    const body = init?.body ? JSON.parse(String(init.body)) : null;
    calls.push({ path, body });
    if (path.endsWith("/preference")) {
      if (init?.method === "PUT") enabled = body.enabled;
      return new Response(JSON.stringify({ enabled }), { status: 200 });
    }
    return new Response(JSON.stringify({ accepted: true }), { status: 202 });
  };
  try {
    await trackProductEvent("unloaded-account", "timer_started", "timer");
    assert.equal(calls.length, 0);
    await getAnalyticsPreference("consent-account");
    await trackProductEvent("consent-account", "timer_started", "timer");
    assert.equal(calls.length, 1);
    await setAnalyticsPreference("consent-account", true);
    await trackProductEvent(
      "consent-account",
      "timer_started",
      "timer",
      "00000000-0000-4000-8000-000000000001",
    );
    const event = calls.find((c) => c.path.endsWith("/events"))!;
    assert.deepEqual(event.body, {
      event_name: "timer_started",
      feature: "timer",
      request_id: "00000000-0000-4000-8000-000000000001",
    });
    assert.equal(calls.filter((c) => c.path.endsWith("/events")).length, 1);
    await trackProductEvent("other-account", "timer_started", "timer");
    await setAnalyticsPreference("consent-account", false);
    await trackProductEvent("consent-account", "timer_started", "timer");
    assert.equal(calls.filter((c) => c.path.endsWith("/events")).length, 1);
  } finally {
    globalThis.fetch = original;
  }
});
test("retry identities are stable, valid UUIDs and do not contain their input", async () => {
  const id = await productEventIdentity("flow:123:start");
  assert.equal(id, await productEventIdentity("flow:123:start"));
  assert.notEqual(id, await productEventIdentity("flow:123:finish"));
  assert.match(
    id,
    /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/,
  );
});
test("empty denominators remain distinct from measured zero", () => {
  assert.equal(percent(null), "Insufficient data");
  assert.equal(percent(0), "0.0%");
});
