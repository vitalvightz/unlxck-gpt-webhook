import assert from "node:assert/strict";
import test from "node:test";
import { beginApiMeasurement, measuredApiFetch, safeEndpoint } from "./api-measurements";

test("capture counts failed retries and redacts dynamic values", async () => {
  const original = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    if (++calls === 1) throw new Error("private medical details");
    return new Response("{}", { headers: { "content-length": "2" } });
  };
  const finish = beginApiMeasurement("history", "navigation");
  try {
    await assert.rejects(measuredApiFetch("/api/plans/private-user?token=secret", "https://test", {}));
    await measuredApiFetch("/api/plans/private-user?token=secret", "https://test", {});
    await measuredApiFetch("/api/plans/different-user", "https://test", {});
    const result = finish();
    assert.equal(result.requests.length, 3);
    assert.deepEqual(result.requests.map(r => r.repeated), [false, true, false]);
    assert.equal(result.requests[0].failed, true);
    assert.equal(result.requests[0].responseBytes, null);
    assert.equal(result.requests[1].responseBytes, 2);
    assert.doesNotMatch(JSON.stringify(result), /private|secret|different-user|medical/);
  } finally { finish(); globalThis.fetch = original; }
});

test("disabled fetch preserves response and errors; overlapping captures rejected", async () => {
  const original = globalThis.fetch;
  const response = new Response("{}");
  const error = new Error("same error");
  try {
    globalThis.fetch = async () => response;
    assert.equal(await measuredApiFetch("/api/me", "https://test", {}), response);
    globalThis.fetch = async () => { throw error; };
    await assert.rejects(measuredApiFetch("/api/me", "https://test", {}), e => e === error);
    const finish = beginApiMeasurement("today", "refresh");
    assert.throws(() => beginApiMeasurement("home", "navigation"));
    finish();
    assert.equal(safeEndpoint("/api/arbitrary-medical-data?id=private"), "/api/:other");
  } finally { globalThis.fetch = original; }
});

test("body completion is separate and differing mutations aren't duplicate reads", async () => {
  const { completeApiMeasurement } = await import("./api-measurements");
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response("{}");
  const finish = beginApiMeasurement("session_save", "mutation");
  try {
    const response = await measuredApiFetch("/api/today/exercise-log", "https://test", { method: "POST", body: "private-one" });
    await response.json();
    completeApiMeasurement(response);
    await measuredApiFetch("/api/today/exercise-log", "https://test", { method: "POST", body: "private-two" });
    const result = finish();
    assert.ok(result.requests[0].bodyCompleteMs! >= result.requests[0].headersMs);
    assert.equal(result.requests[0].responseBytes, null);
    assert.equal(result.requests[1].repeated, false);
    assert.doesNotMatch(JSON.stringify(result), /private/);
  } finally { finish(); globalThis.fetch = original; }
});
