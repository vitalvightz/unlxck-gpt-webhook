import { expect, test } from "@playwright/test";

import { isolateFromNetwork, PUBLIC_ROUTES } from "./support";

const BASE_URL = "http://127.0.0.1:3100";

test.describe("public routes load without crashing", () => {
  for (const route of PUBLIC_ROUTES) {
    test(`GET ${route} renders the app shell`, async ({ page, baseURL }) => {
      await isolateFromNetwork(page, baseURL ?? BASE_URL);

      const uncaughtErrors: string[] = [];
      page.on("pageerror", (error) => uncaughtErrors.push(error.message));

      const response = await page.goto(route, { waitUntil: "domcontentloaded" });

      // No server error page on primary routes.
      expect(response, `expected a response for ${route}`).not.toBeNull();
      expect(response!.status(), `unexpected status for ${route}`).toBeLessThan(500);

      // Document has a non-empty title (basic a11y / SEO sanity).
      await expect(page).toHaveTitle(/.+/);

      // App shell renders its main landmark from the root layout.
      await expect(page.locator("main")).toBeVisible();

      // No console-breaking uncaught exceptions during initial render.
      expect(uncaughtErrors, `uncaught errors on ${route}: ${uncaughtErrors.join("; ")}`).toEqual([]);
    });
  }
});

test("app shell and navigation render for an anonymous visitor", async ({ page, baseURL }) => {
  await isolateFromNetwork(page, baseURL ?? BASE_URL);
  await page.goto("/", { waitUntil: "domcontentloaded" });

  // The persistent sidebar shell renders on every route at desktop widths.
  // (The semantic <nav> only renders once a session is hydrated, so we anchor
  // on the always-present shell + its anonymous access links instead.)
  const sidebar = page.locator("#app-sidebar");
  await expect(sidebar).toBeVisible();

  // Anonymous visitors get a navigable login link in the public shell.
  await expect(page.getByLabel("Account access").getByRole("link", { name: /log in/i })).toBeVisible();
});

test("protected route redirects unauthenticated users to login", async ({ page, baseURL }) => {
  await isolateFromNetwork(page, baseURL ?? BASE_URL);

  await page.goto("/generate", { waitUntil: "domcontentloaded" });

  // RequireAuth performs a client-side replace to /login when no session exists.
  await page.waitForURL("**/login", { timeout: 15_000 });
  expect(page.url()).toContain("/login");
});
