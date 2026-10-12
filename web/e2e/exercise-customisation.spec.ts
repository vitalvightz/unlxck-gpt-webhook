import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { isolateFromNetwork } from "./support";

/**
 * Swap / add / remove from Today's Enhanced Card, end to end against the real
 * API (ranking, override writes, effective plan reads) served over an
 * in-memory store: python tools/e2e_exercise_customisation_server.py
 */
const api = process.env.EXERCISE_TEST_API;
const storageKey = `sb-${new URL(process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://stub.supabase.co").hostname.split(".")[0]}-auth-token`;
const shots = process.env.EXERCISE_SCREENSHOTS;

async function setup(page: Page, baseURL: string) {
  await isolateFromNetwork(page, baseURL);
  await page.route("https://fonts.googleapis.com/**", (route) => route.fulfill({ contentType: "text/css", body: "" }));
  await page.addInitScript(([key, value]) => localStorage.setItem(key, value), [storageKey, JSON.stringify({
    access_token: "athlete-token", refresh_token: "test-refresh", token_type: "bearer",
    expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
    user: { id: "athlete-1", email: "ari@example.com", aud: "authenticated", role: "authenticated", app_metadata: {}, user_metadata: {} },
  })]);
  const writes: { path: string; body: unknown }[] = [];
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const response = await page.request.fetch(`${api}${url.pathname}${url.search}`, {
      method: request.method(),
      headers: { Authorization: "Bearer athlete-token", "Content-Type": "application/json" },
      data: request.postData() ?? undefined,
      failOnStatusCode: false,
    });
    if (request.method() === "POST" && url.pathname.includes("/exercise-changes")) {
      writes.push({ path: url.pathname, body: request.postDataJSON() });
    }
    if (url.pathname === "/api/me" && response.ok()) {
      const me = await response.json();
      // The seeded athlete has completed onboarding and consent.
      Object.assign(me.profile, {
        athlete_timezone: "UTC", technical_style: ["boxing"], date_of_birth: "1995-01-01", meets_minimum_age: true,
        is_minor: false, terms_accepted: true, health_consent_granted: true, private_trial_ack_at: "2026-01-01T12:00:00Z",
      });
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(me) });
    }
    return route.fulfill({ status: response.status(), contentType: "application/json", body: await response.body() });
  });
  return writes;
}

/** Let the sheet's enter animation finish before a screenshot. */
async function settle(page: Page) {
  await page.waitForTimeout(300);
}

test.describe.configure({ mode: "serial" });

for (const width of [320, 390, 1280]) {
  test(`Today: swap, undo, remove and add without leaving Today (${width}px)`, async ({ page, baseURL }) => {
    test.skip(!api, "Run with EXERCISE_TEST_API pointing at tools/e2e_exercise_customisation_server.py");
    expect((await page.request.post(`${api}/__e2e/reset`)).ok()).toBe(true);
    await page.setViewportSize({ width, height: 844 });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const writes = await setup(page, baseURL!);

    await page.goto("/today");
    const squat = page.getByRole("button", { name: "Change Back Squat", exact: true });
    await expect(squat).toBeVisible();
    const startUrl = page.url();
    // No horizontal overflow from the new control at any width.
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

    // Swap: three dots -> Swap -> pick -> updated in place, with Undo.
    await squat.click();
    const menu = page.getByRole("dialog", { name: "Back Squat" });
    await expect(menu.getByRole("group", { name: "Change Back Squat" })).toBeVisible();
    const actions = menu.getByRole("group", { name: "Change Back Squat" }).getByRole("button");
    const boxes = await Promise.all((await actions.all()).map((action) => action.boundingBox()));
    // One horizontal bar: every action shares a row.
    expect(new Set(boxes.map((box) => Math.round(box!.y))).size).toBe(1);
    if (shots) await settle(page), await page.screenshot({ path: `${shots}/menu-${width}.png` });
    await menu.getByRole("button", { name: "Swap", exact: true }).click();
    const sheet = page.getByRole("dialog", { name: "Swap Back Squat" });
    const option = sheet.getByRole("button", { name: /Cossack Squat/ });
    await expect(option).toBeVisible();
    await expect(sheet.getByRole("radio", { name: "Just this workout" })).toHaveAttribute("aria-checked", "true");
    await expect(sheet.getByText("4 × 5 · RPE 7").first()).toBeVisible();
    expect((await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations).toEqual([]);
    expect(await sheet.evaluate((panel) => panel.scrollWidth <= panel.clientWidth)).toBe(true);
    if (shots) await settle(page), await page.screenshot({ path: `${shots}/swap-sheet-${width}.png` });
    await option.click();
    await expect(sheet).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Change Cossack Squat", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Change Back Squat", exact: true })).toHaveCount(0);
    await expect(page.getByText("Swapped to Cossack Squat")).toBeVisible();
    if (shots) await settle(page), await page.screenshot({ path: `${shots}/swapped-${width}.png` });

    // Undo restores the prescription.
    await page.getByRole("button", { name: "Undo", exact: true }).click();
    await expect(page.getByRole("button", { name: "Change Back Squat", exact: true })).toBeVisible();

    // Remove an accessory: no confirmation, a short Undo, and Restore on the card.
    await page.getByRole("button", { name: "Change Front Plank", exact: true }).click();
    await page.getByRole("button", { name: "Remove Front Plank", exact: true }).click();
    await expect(page.getByRole("button", { name: "Change Front Plank", exact: true })).toHaveCount(0);
    const restore = page.getByRole("button", { name: "Restore Front Plank", exact: true });
    await expect(restore).toBeVisible();
    // Add and Restore share the session's foot line.
    const [addBox, restoreBox] = await Promise.all([
      page.getByRole("button", { name: "Add exercise" }).boundingBox(), restore.boundingBox(),
    ]);
    expect(Math.abs(addBox!.y - restoreBox!.y)).toBeLessThan(4);
    if (shots) await settle(page), await page.screenshot({ path: `${shots}/removed-${width}.png` });
    await restore.click();
    await expect(page.getByRole("button", { name: "Change Front Plank", exact: true })).toBeVisible();

    // Add: anything from the library, searched inside the sheet.
    await page.getByRole("button", { name: "Add exercise" }).click();
    const add = page.getByRole("dialog", { name: "Add exercise" });
    await expect(add.locator("ul > li").first()).toBeVisible();
    await add.getByRole("searchbox", { name: "Search the exercise library" }).fill("sled push");
    const first = add.locator("ul:not([data-refreshing='true']) > li").filter({ hasText: /sled/i }).first();
    await expect(first).toBeVisible();
    // Nothing inside the sheet runs off its edge, search field included.
    expect(await add.evaluate((panel) => panel.scrollWidth <= panel.clientWidth)).toBe(true);
    if (shots) await settle(page), await page.screenshot({ path: `${shots}/library-search-${width}.png` });
    const name = (await first.locator("button").first().locator("span span").first().textContent())!.trim();
    await first.locator("button").first().click();
    const doseForm = first.locator("form");
    if (await doseForm.count()) {
      if (shots) await settle(page), await page.screenshot({ path: `${shots}/dose-${width}.png` });
      const inputs = doseForm.locator("input");
      await inputs.nth(0).fill("3");
      await inputs.nth(1).fill("20");
      await inputs.nth(2).fill("60");
      await doseForm.getByRole("button", { name: "Add" }).click();
    }
    await expect(add).toHaveCount(0);
    await expect(page.getByRole("button", { name: `Change ${name}`, exact: true })).toBeVisible();
    // One confirmation at a time, never a stack of toasts.
    await expect(page.locator(".toast")).toHaveCount(1);
    if (shots) await settle(page), await page.screenshot({ path: `${shots}/added-${width}.png` });

    expect(page.url()).toBe(startUrl);
    expect(writes.filter((write) => write.path.endsWith("/exercise-changes"))).toHaveLength(3);
    expect(errors).toEqual([]);
  });
}
