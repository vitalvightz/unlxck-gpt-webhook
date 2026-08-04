import { expect, test } from "@playwright/test";

/**
 * Covers the three response-header changes only. The Content-Security-Policy is
 * asserted elsewhere (e2e/pwa.spec.ts) and is unchanged by them.
 */

test("responses omit X-Powered-By and carry the cross-origin policies", async ({ request }) => {
  const headers = (await request.get("/")).headers();

  expect(headers["x-powered-by"]).toBeUndefined();
  expect(headers["cross-origin-opener-policy"]).toBe("same-origin");
  expect(headers["cross-origin-resource-policy"]).toBe("same-origin");
  // COEP would have to be negotiated with Cloudflare Turnstile and Google Fonts
  // first, so it stays off.
  expect(headers["cross-origin-embedder-policy"]).toBeUndefined();
});

test("static assets get the same treatment", async ({ request }) => {
  const response = await request.get("/favicon.ico");

  expect(response.status()).toBe(200);
  expect(response.headers()["x-powered-by"]).toBeUndefined();
  expect(response.headers()["cross-origin-opener-policy"]).toBe("same-origin");
  expect(response.headers()["cross-origin-resource-policy"]).toBe("same-origin");
});
