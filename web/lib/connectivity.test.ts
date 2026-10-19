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
  reportNetworkSuccess,
  subscribeConnectivity,
} from "@/lib/connectivity";

afterEach(() => __resetConnectivityForTests());

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

test("store flips to degraded on failure and back on success, notifying once each way", () => {
  let notifications = 0;
  const unsubscribe = subscribeConnectivity(() => {
    notifications += 1;
  });
  reportNetworkFailure();
  reportNetworkFailure();
  assert.deepEqual(getConnectivitySnapshot(), { offline: false, degraded: true });
  reportNetworkSuccess();
  reportNetworkSuccess();
  assert.deepEqual(getConnectivitySnapshot(), { offline: false, degraded: false });
  assert.equal(notifications, 2);
  unsubscribe();
});
