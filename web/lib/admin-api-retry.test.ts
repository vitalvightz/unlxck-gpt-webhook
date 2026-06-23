import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import test, { afterEach, beforeEach } from "node:test";

import {
  ApiError,
  RETRYABLE_NETWORK_MESSAGE,
  archivePlan,
  getAdminAthlete,
  getAdminAthleteNutritionCurrent,
  isRetryableApiFailure,
  listAdminAthletes,
  listAdminPlans,
  updateAdminAthleteNutritionCurrent,
} from "./api.ts";

const ADMIN_READ_HELPERS = [
  "listAdminAthletes",
  "getAdminAthlete",
  "getAdminAthleteNutritionCurrent",
  "updateAdminAthleteNutritionCurrent",
  "listAdminPlans",
] as const;

const realFetch = globalThis.fetch;
const realSetTimeout = globalThis.setTimeout;
const realConsoleInfo = console.info;
const realConsoleWarn = console.warn;
const realConsoleError = console.error;

beforeEach(() => {
  // Collapse backoff sleeps so retries resolve instantly.
  (globalThis as { setTimeout: typeof globalThis.setTimeout }).setTimeout = ((
    callback: (...args: unknown[]) => void,
  ) => {
    Promise.resolve().then(() => callback());
    return 0 as unknown as ReturnType<typeof globalThis.setTimeout>;
  }) as typeof globalThis.setTimeout;
  // Silence the request lifecycle logs emitted by readJson during retries.
  console.info = () => {};
  console.warn = () => {};
  console.error = () => {};
});

afterEach(() => {
  globalThis.fetch = realFetch;
  globalThis.setTimeout = realSetTimeout;
  console.info = realConsoleInfo;
  console.warn = realConsoleWarn;
  console.error = realConsoleError;
});

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function gatewayResponse(status: number): Response {
  return new Response("<!doctype html><html><body>upstream blip</body></html>", {
    status,
    headers: { "Content-Type": "text/html" },
  });
}

test("isRetryableApiFailure treats 401/403/404 as non-retryable", () => {
  assert.equal(isRetryableApiFailure(new ApiError("unauthorized", 401)), false);
  assert.equal(isRetryableApiFailure(new ApiError("forbidden", 403)), false);
  assert.equal(isRetryableApiFailure(new ApiError("not found", 404)), false);
});

test("isRetryableApiFailure treats 502/503/504 as retryable", () => {
  assert.equal(isRetryableApiFailure(new ApiError("bad gateway", 502)), true);
  assert.equal(isRetryableApiFailure(new ApiError("unavailable", 503)), true);
  assert.equal(isRetryableApiFailure(new ApiError("timeout", 504)), true);
});

test("isRetryableApiFailure treats network errors as retryable", () => {
  assert.equal(isRetryableApiFailure(new Error(RETRYABLE_NETWORK_MESSAGE)), true);
});

test("isRetryableApiFailure ignores plain client errors like 400", () => {
  assert.equal(isRetryableApiFailure(new ApiError("bad request", 400)), false);
  assert.equal(isRetryableApiFailure(new ApiError("conflict", 409)), false);
});

test("listAdminAthletes retries on a transient 503 then succeeds", async () => {
  const calls: string[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    calls.push(String(input));
    if (calls.length === 1) {
      return gatewayResponse(503);
    }
    return jsonResponse(200, []);
  }) as typeof fetch;

  const result = await listAdminAthletes("token");
  assert.deepEqual(result, []);
  assert.equal(calls.length, 2, "should retry once after a 503");
});

test("listAdminAthletes forwards q/limit/offset as encoded query params", async () => {
  const calls: string[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    calls.push(String(input));
    return jsonResponse(200, []);
  }) as typeof fetch;

  await listAdminAthletes("token", { q: "ari & co", limit: 20, offset: 40 });

  assert.equal(calls.length, 1);
  const url = new URL(calls[0]!);
  assert.equal(url.pathname, "/api/admin/athletes");
  assert.equal(url.searchParams.get("q"), "ari & co");
  assert.equal(url.searchParams.get("limit"), "20");
  assert.equal(url.searchParams.get("offset"), "40");
});

test("listAdminPlans omits the q param when the search term is blank", async () => {
  const calls: string[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    calls.push(String(input));
    return jsonResponse(200, []);
  }) as typeof fetch;

  await listAdminPlans("token", { q: "   ", limit: 20, offset: 0 });

  assert.equal(calls.length, 1);
  const url = new URL(calls[0]!);
  assert.equal(url.searchParams.has("q"), false);
  assert.equal(url.searchParams.get("limit"), "20");
  assert.equal(url.searchParams.get("offset"), "0");
});

test("getAdminAthlete does not retry on 403", async () => {
  let attempts = 0;
  globalThis.fetch = (async () => {
    attempts += 1;
    return jsonResponse(403, { detail: "forbidden" });
  }) as typeof fetch;

  await assert.rejects(
    getAdminAthlete("token", "athlete-1"),
    (raised: unknown) => raised instanceof ApiError && raised.status === 403,
  );
  assert.equal(attempts, 1, "403 must surface immediately without retrying");
});

test("getAdminAthleteNutritionCurrent does not retry on 404", async () => {
  let attempts = 0;
  globalThis.fetch = (async () => {
    attempts += 1;
    return jsonResponse(404, { detail: "missing" });
  }) as typeof fetch;

  await assert.rejects(
    getAdminAthleteNutritionCurrent("token", "athlete-1"),
    (raised: unknown) => raised instanceof ApiError && raised.status === 404,
  );
  assert.equal(attempts, 1);
});

test("updateAdminAthleteNutritionCurrent retries the idempotent PUT on 502", async () => {
  let attempts = 0;
  globalThis.fetch = (async () => {
    attempts += 1;
    if (attempts < 2) {
      return gatewayResponse(502);
    }
    return jsonResponse(200, { ok: true });
  }) as typeof fetch;

  const result = await updateAdminAthleteNutritionCurrent("token", "athlete-1", {
    nutrition_profile: null,
    shared_camp_context: null,
    s_and_c_preferences: null,
    nutrition_readiness: null,
    nutrition_monitoring: null,
    nutrition_coach_controls: null,
  } as never);
  assert.deepEqual(result, { ok: true });
  assert.equal(attempts, 2);
});

test("listAdminPlans gives up after configured attempts on persistent 503", async () => {
  let attempts = 0;
  globalThis.fetch = (async () => {
    attempts += 1;
    return gatewayResponse(503);
  }) as typeof fetch;

  await assert.rejects(
    listAdminPlans("token"),
    (raised: unknown) => raised instanceof ApiError && raised.status === 503,
  );
  assert.equal(attempts, 3, "withTransientRetries defaults to 3 attempts");
});

test("archivePlan resolves on 204 No Content via the shared request pipeline", async () => {
  const calls: { url: string; method: string; auth: string | null }[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const headers = new Headers(init?.headers ?? {});
    calls.push({
      url: String(input),
      method: init?.method ?? "GET",
      auth: headers.get("authorization"),
    });
    return new Response(null, { status: 204 });
  }) as typeof fetch;

  await archivePlan("delete-token", "plan-42");

  assert.equal(calls.length, 1);
  assert.equal(calls[0]?.method, "DELETE");
  assert.equal(calls[0]?.auth, "Bearer delete-token");
  assert.match(calls[0]?.url ?? "", /\/api\/plans\/plan-42$/);
});

test("archivePlan retries the idempotent DELETE on 503 then succeeds", async () => {
  let attempts = 0;
  globalThis.fetch = (async () => {
    attempts += 1;
    if (attempts === 1) {
      return gatewayResponse(503);
    }
    return new Response(null, { status: 204 });
  }) as typeof fetch;

  await archivePlan("token", "plan-1");
  assert.equal(attempts, 2);
});

test("archivePlan surfaces a 404 ApiError without retrying", async () => {
  let attempts = 0;
  globalThis.fetch = (async () => {
    attempts += 1;
    return jsonResponse(404, { detail: "plan not found" });
  }) as typeof fetch;

  await assert.rejects(
    archivePlan("token", "missing-plan"),
    (raised: unknown) => raised instanceof ApiError && raised.status === 404,
  );
  assert.equal(attempts, 1);
});

test("admin read helpers are wrapped in withTransientRetries (source regression)", () => {
  const apiPath = resolve(dirname(fileURLToPath(import.meta.url)), "api.ts");
  const source = readFileSync(apiPath, "utf8");
  for (const name of ADMIN_READ_HELPERS) {
    const exportPattern = new RegExp(
      `export function ${name}[\\s\\S]*?\\n\\}\\n`,
      "m",
    );
    const block = source.match(exportPattern);
    assert.ok(block, `expected to find body for ${name} in api.ts`);
    assert.match(
      block![0],
      /withTransientRetries\(/,
      `${name} must be wrapped in withTransientRetries so transient blips are retried`,
    );
  }
});
