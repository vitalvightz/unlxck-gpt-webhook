import assert from "node:assert/strict";
import { afterEach, test } from "node:test";

import {
  OFFLINE_NETWORK_MESSAGE,
  RETRYABLE_NETWORK_MESSAGE,
  __resetConnectivityForTests,
  describeLoadFailure,
  getConnectivitySnapshot,
  isNetworkFailure,
  reportNetworkFailure,
  checkApiConnection,
  RECONNECTED_EVENT,
  reloadAfterRecovery,
  subscribeConnectivity,
} from "@/lib/connectivity";

const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
const originalNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");
const originalFetch = globalThis.fetch;

afterEach(() => {
  __resetConnectivityForTests();
  globalThis.fetch = originalFetch;
  if (originalWindow) Object.defineProperty(globalThis, "window", originalWindow);
  else Reflect.deleteProperty(globalThis, "window");
  if (originalNavigator) Object.defineProperty(globalThis, "navigator", originalNavigator);
  else Reflect.deleteProperty(globalThis, "navigator");
});

function browser() {
  let online = true;
  let reloads = 0;
  const target = Object.assign(new EventTarget(), {
    location: { pathname: "/plans/original", search: "?week=2", reload: () => { reloads += 1; } },
    history: { state: null as unknown, replaceState(value: unknown) { this.state = value; } },
  });
  Object.defineProperty(globalThis, "window", { configurable: true, value: target });
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: { get onLine() { return online; } } });
  return { target, setOnline(value: boolean) { online = value; target.dispatchEvent(new Event(value ? "online" : "offline")); }, reloads: () => reloads };
}

function healthyResponse() {
  return Response.json({ ok: true, app: "unlxck-fight-camp-api" });
}

test("classifies connection failures, not server answers", () => {
  assert.equal(isNetworkFailure(new Error(RETRYABLE_NETWORK_MESSAGE)), true);
  assert.equal(isNetworkFailure(new Error(OFFLINE_NETWORK_MESSAGE)), true);
  assert.equal(isNetworkFailure(new TypeError("Failed to fetch")), true);
  assert.equal(isNetworkFailure(new TypeError("Load failed")), true);
  const chunk = new Error("Loading chunk 412 failed.");
  chunk.name = "ChunkLoadError";
  assert.equal(isNetworkFailure(chunk), true);
  assert.equal(isNetworkFailure(new Error("Plan not found")), false);
  assert.equal(isNetworkFailure("nope"), false);
});

test("describeLoadFailure keeps the caller's copy for real server errors", () => {
  assert.equal(describeLoadFailure(new Error("Plan not found"), "fallback"), "fallback");
  assert.equal(describeLoadFailure(new TypeError("Failed to fetch"), "fallback"), RETRYABLE_NETWORK_MESSAGE);
});

test("store only recovers after a validated health check, notifying once each way", async () => {
  globalThis.fetch = async () => healthyResponse();
  let notifications = 0;
  const unsubscribe = subscribeConnectivity(() => {
    notifications += 1;
  });
  reportNetworkFailure();
  reportNetworkFailure();
  assert.deepEqual(getConnectivitySnapshot(), { offline: false, degraded: true });
  await checkApiConnection();
  await checkApiConnection();
  assert.deepEqual(getConnectivitySnapshot(), { offline: false, degraded: false });
  assert.equal(notifications, 2);
  unsubscribe();
});


test("browser reconnect stays degraded until UNLXCK API confirms recovery", async () => {
  const device = browser();
  let resolveHealth!: (response: Response) => void;
  let checks = 0;
  globalThis.fetch = async (url, init) => {
    assert.equal(url, "/api/health");
    assert.equal(init?.cache, "no-store");
    checks += 1;
    return new Promise<Response>((resolve) => { resolveHealth = resolve; });
  };
  let recoveries = 0;
  device.target.addEventListener(RECONNECTED_EVENT, () => { recoveries += 1; });
  const unsubscribe = subscribeConnectivity(() => {});
  device.setOnline(false);
  assert.deepEqual(getConnectivitySnapshot(), { offline: true, degraded: false });
  device.setOnline(true);
  device.target.dispatchEvent(new Event("online"));
  assert.deepEqual(getConnectivitySnapshot(), { offline: false, degraded: true });
  assert.equal(recoveries, 0);
  const pending = checkApiConnection();
  assert.equal(pending, checkApiConnection(), "concurrent checks share a request");
  assert.equal(checks, 1);
  resolveHealth(healthyResponse());
  assert.equal(await pending, true);
  assert.equal(recoveries, 1);
  assert.deepEqual(getConnectivitySnapshot(), { offline: false, degraded: false });
  unsubscribe();
});

test("unrelated successful API calls cannot clear a failure", async () => {
  const { getCustomPlan } = await import("@/lib/api");
  globalThis.fetch = async () => Response.json({ id: "another-plan" });
  reportNetworkFailure();
  await getCustomPlan("test-token", "another-plan");
  assert.deepEqual(getConnectivitySnapshot(), { offline: false, degraded: true });
});

test("a health response started before a newer failure cannot announce recovery", async () => {
  browser();
  let resolveHealth!: (response: Response) => void;
  globalThis.fetch = () => new Promise<Response>((resolve) => { resolveHealth = resolve; });
  reportNetworkFailure();
  const pending = checkApiConnection();
  reportNetworkFailure();
  resolveHealth(healthyResponse());
  assert.equal(await pending, false);
  assert.equal(getConnectivitySnapshot().degraded, true);
});

test("going offline invalidates an in-flight successful check", async () => {
  const device = browser();
  let resolveHealth!: (response: Response) => void;
  globalThis.fetch = () => new Promise<Response>((resolve) => { resolveHealth = resolve; });
  getConnectivitySnapshot();
  reportNetworkFailure();
  const pending = checkApiConnection();
  device.setOnline(false);
  resolveHealth(healthyResponse());
  assert.equal(await pending, false);
  assert.equal(getConnectivitySnapshot().offline, true);
});

test("gateway, auth, captive portal and malformed health answers never confirm recovery", async () => {
  for (const response of [
    new Response("unavailable", { status: 503 }),
    Response.json({ detail: "unauthenticated" }, { status: 401 }),
    new Response("<html>Wi-Fi sign in</html>", { headers: { "content-type": "text/html" } }),
    Response.json({ ok: true, app: "something-else" }),
    Response.json({ ok: false, app: "unlxck-fight-camp-api" }),
    new Response("{broken", { headers: { "content-type": "application/json" } }),
  ]) {
    globalThis.fetch = async () => response;
    reportNetworkFailure();
    assert.equal(await checkApiConnection(), false);
    assert.equal(getConnectivitySnapshot().degraded, true);
  }
});

test("a hanging recovery request times out and permits a later retry", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  globalThis.fetch = (_url, init) => new Promise<Response>((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new Error("timed out")), { once: true });
  });
  reportNetworkFailure();
  const pending = checkApiConnection();
  t.mock.timers.tick(8000);
  assert.equal(await pending, false);
  globalThis.fetch = async () => healthyResponse();
  assert.equal(await checkApiConnection(), true);
});

test("automatic reloads are limited even if health recovers but a chunk remains unavailable", () => {
  const device = browser();
  assert.equal(reloadAfterRecovery(), true);
  assert.equal(reloadAfterRecovery(), false);
  assert.equal(device.reloads(), 1);
  assert.equal(reloadAfterRecovery(true), true, "an explicit retry can override the cooldown");
  assert.equal(device.reloads(), 2);
});

test("history update denial cannot cause an automatic reload loop", () => {
  const device = browser();
  device.target.history.replaceState = () => { throw new Error("history update denied"); };
  assert.equal(reloadAfterRecovery(), false);
  assert.equal(device.reloads(), 0);
  assert.equal(reloadAfterRecovery(true), true);
  assert.equal(device.reloads(), 1);
});
