import { expect, test } from "@playwright/test";

import { isolateFromNetwork } from "./support";

const BASE_URL = "http://127.0.0.1:3100";

test("manifest, service worker, icon, and offline assets are production-ready", async ({ request }) => {
  const manifestResponse = await request.get("/manifest.webmanifest");
  expect(manifestResponse.status()).toBe(200);
  expect(manifestResponse.headers()["content-type"]).toContain("application/manifest+json");
  const manifest = await manifestResponse.json();
  expect(manifest).toMatchObject({
    id: "/",
    name: "UNLXCK",
    short_name: "UNLXCK",
    start_url: "/dashboard?source=pwa",
    scope: "/",
    display: "standalone",
  });

  const workerResponse = await request.get("/sw.js?build=headers-check");
  expect(workerResponse.status()).toBe(200);
  expect(workerResponse.headers()["content-type"]).toContain("application/javascript");
  expect(workerResponse.headers()["cache-control"]).toContain("no-cache");
  expect(workerResponse.headers()["cache-control"]).toContain("no-store");
  expect(workerResponse.headers()["cache-control"]).toContain("must-revalidate");
  expect(workerResponse.headers()["service-worker-allowed"]).toBe("/");
  expect(workerResponse.headers()["content-security-policy"]).toBe(
    "default-src 'self'; base-uri 'none'; connect-src 'self'; object-src 'none'; script-src 'self'",
  );

  const rootResponse = await request.get("/");
  const rootCsp = rootResponse.headers()["content-security-policy"] ?? "";
  expect(rootCsp).toMatch(/script-src 'self' 'nonce-[^']+' 'strict-dynamic'/);
  expect(rootCsp).toContain("worker-src 'self' blob:");
  expect(rootCsp).toContain("manifest-src 'self'");

  for (const path of [
    "/icons/icon-192x192.png",
    "/icons/icon-512x512.png",
    "/icons/icon-maskable-512x512.png",
    "/icons/apple-touch-icon.png",
    "/offline.html",
  ]) {
    const response = await request.get(path);
    expect(response.status(), path).toBe(200);
  }
});

test("root-scoped worker caches only the offline shell and static assets", async ({
  page,
  baseURL,
}) => {
  await isolateFromNetwork(page, baseURL ?? BASE_URL);
  await page.goto("/", { waitUntil: "domcontentloaded" });

  const registration = await page.evaluate(async () => {
    const ready = await navigator.serviceWorker.ready;
    await fetch("/api/health").catch(() => null);
    return {
      scope: ready.scope,
      scriptURL: ready.active?.scriptURL ?? ready.waiting?.scriptURL ?? "",
    };
  });

  expect(registration.scope).toBe(`${new URL(baseURL ?? BASE_URL).origin}/`);
  expect(registration.scriptURL).toContain("/sw.js?build=");

  const cachedUrls = await page.evaluate(async () => {
    const names = await caches.keys();
    const urls = await Promise.all(
      names.map(async (name) => (await (await caches.open(name)).keys()).map((request) => request.url)),
    );
    return urls.flat();
  });

  expect(cachedUrls.length).toBeGreaterThan(0);
  for (const value of cachedUrls) {
    const url = new URL(value);
    expect(
      url.pathname === "/offline.html" ||
        url.pathname.startsWith("/icons/") ||
        url.pathname.startsWith("/_next/static/"),
      value,
    ).toBe(true);
  }
  for (const forbidden of [
    "/api/",
    "/plans",
    "/profiles",
    "generation_jobs",
    "/check-ins",
    "/nutrition",
    "/admin",
  ]) {
    expect(cachedUrls.some((value) => value.includes(forbidden)), forbidden).toBe(false);
  }
});

test("registered worker serves the honest offline fallback and recovers", async ({ page, context, baseURL }) => {
  await isolateFromNetwork(page, baseURL ?? BASE_URL);
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) {
      await new Promise<void>((resolve) =>
        navigator.serviceWorker.addEventListener("controllerchange", () => resolve(), { once: true }),
      );
    }
  });

  await context.setOffline(true);
  try {
    await page.goto("/dashboard?offline-test=1", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "UNLXCK can’t connect right now." })).toBeVisible();
    await expect(page.getByRole("button", { name: "Retry connection" })).toBeVisible();
  } finally {
    await context.setOffline(false);
  }

  await page.getByRole("button", { name: "Retry connection" }).click();
  await page.waitForURL(/\/(dashboard|login)(\?|$)/);
  expect(page.url()).not.toContain("offline-test=1");
});
