import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { isolateFromNetwork } from "./support";

// Report must be generated from the disposable empty database by the validation
// procedure in docs/product-analytics.md. Auth is a local test identity only.
const reportPath = process.env.ANALYTICS_REPORT_JSON;
const identityPath = process.env.ANALYTICS_ADMIN_JSON;
for (const width of [390, 1280]) {
  test(`admin product analytics empty-data filters and responsive layout (${width})`, async ({
    page,
    baseURL,
  }) => {
    test.skip(
      !reportPath || !identityPath,
      "Supply a real local empty-database report and local admin identity.",
    );
    const report = JSON.parse(readFileSync(reportPath!, "utf8"));
    const identity = JSON.parse(readFileSync(identityPath!, "utf8"));
    await isolateFromNetwork(page, baseURL!);
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() =>
      localStorage.setItem(
        "sb-stub-auth-token",
        JSON.stringify({
          access_token: "admin-token",
          refresh_token: "local-test",
          token_type: "bearer",
          expires_in: 86400,
          expires_at: Math.floor(Date.now() / 1000) + 86400,
          user: {
            id: "admin-1",
            email: "admin@example.com",
            aud: "authenticated",
            role: "authenticated",
            app_metadata: {},
            user_metadata: {},
          },
        }),
      ),
    );
    const requests: string[] = [];
    let failNext = false;
    await page.route("**/api/**", async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/api/me") return route.fulfill({ json: identity });
      if (url.pathname === "/api/admin/product-analytics") {
        requests.push(url.search);
        if (failNext) {
          failNext = false;
          return route.fulfill({
            status: 503,
            json: { detail: "Local analytics temporarily unavailable" },
          });
        }
        return route.fulfill({ json: report });
      }
      return route.fulfill({ json: [] });
    });
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto("/admin/analytics");
    await expect(
      page.getByRole("heading", { name: "Product Analytics", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("No eligible athletes match these filters."),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await page
      .getByRole("combobox", { name: "Period", exact: true })
      .selectOption("7");
    await expect.poll(() => requests.at(-1)).toContain("days=7");
    await page
      .getByRole("combobox", { name: "Plan usage", exact: true })
      .selectOption("plan_free");
    await expect.poll(() => requests.at(-1)).toContain("plan_mode=plan_free");
    await page.getByText("Definitions & historical coverage").click();
    await expect(
      page.getByText(/Only fully elapsed return days/),
    ).toBeVisible();
    expect(errors).toEqual([]);
    const shots = process.env.ANALYTICS_SCREENSHOTS;
    if (shots)
      await page.screenshot({
        path: `${shots}/analytics-${width}.png`,
        fullPage: true,
      });
    if (width === 1280) {
      failNext = true;
      await page
        .getByRole("combobox", { name: "Period", exact: true })
        .selectOption("30");
      await expect(
        page
          .getByRole("alert")
          .filter({ hasText: "Local analytics temporarily unavailable" }),
      ).toContainText("Local analytics temporarily unavailable");
      await page.getByRole("button", { name: "Retry", exact: true }).click();
      await expect(
        page.getByText("No eligible athletes match these filters."),
      ).toBeVisible();
    }
  });
}

const athleteProfilePath = process.env.ANALYTICS_ATHLETE_PROFILE_JSON;
const athleteActivityPath = process.env.ANALYTICS_ATHLETE_ACTIVITY_JSON;
test("individual athlete has a verified empty activity summary", async ({
  page,
  baseURL,
}) => {
  test.skip(
    !athleteProfilePath || !athleteActivityPath || !identityPath,
    "Supply a real local empty-athlete report.",
  );
  const athlete = JSON.parse(readFileSync(athleteProfilePath!, "utf8"));
  const activity = JSON.parse(readFileSync(athleteActivityPath!, "utf8"));
  const identity = JSON.parse(readFileSync(identityPath!, "utf8"));
  await isolateFromNetwork(page, baseURL!);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.addInitScript(() =>
    localStorage.setItem(
      "sb-stub-auth-token",
      JSON.stringify({
        access_token: "admin-token",
        refresh_token: "local-test",
        token_type: "bearer",
        expires_in: 86400,
        expires_at: Math.floor(Date.now() / 1000) + 86400,
        user: {
          id: "admin-1",
          email: "admin@example.com",
          aud: "authenticated",
          role: "authenticated",
          app_metadata: {},
          user_metadata: {},
        },
      }),
    ),
  );
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/me") return route.fulfill({ json: identity });
    if (path.endsWith("/activity")) return route.fulfill({ json: activity });
    if (path === `/api/admin/athletes/${athlete.athlete_id}`)
      return route.fulfill({ json: athlete });
    if (path.endsWith("/nutrition/current"))
      return route.fulfill({
        status: 404,
        json: { detail: "No local nutrition workspace" },
      });
    return route.fulfill({ json: [] });
  });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(`/admin/athletes/${athlete.athlete_id}`);
  await expect(
    page.getByRole("heading", { name: "Activity", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Meaningful activity timeline" }),
  ).toBeVisible();
  await expect(
    page.getByText("No recorded activity", { exact: true }).first(),
  ).toBeVisible();
  expect(errors).toEqual([]);
  if (process.env.ANALYTICS_SCREENSHOTS)
    await page.screenshot({
      path: `${process.env.ANALYTICS_SCREENSHOTS}/athlete-activity.png`,
      fullPage: true,
    });
});
