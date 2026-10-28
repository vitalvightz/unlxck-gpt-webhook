import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdirSync } from "node:fs";
import fixtures from "./fixtures/rehab-today.json";
import { isolateFromNetwork } from "./support";

test.use({ hasTouch: true });

async function setup(page: Page, baseURL: string) {
  await isolateFromNetwork(page, baseURL);
  const { view, profile } = structuredClone(fixtures.chest);
  Object.assign(profile.profile, { private_trial_ack_at: "2026-10-05T12:00:00Z" });
  const now = new Date(`${view.today.training_day}T12:05:00Z`);
  await page.clock.setFixedTime(now);
  const key = `sb-${new URL(process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://stub.supabase.co").hostname.split(".")[0]}-auth-token`;
  await page.addInitScript(([key, value]) => localStorage.setItem(key, value), [key, JSON.stringify({
    access_token: "athlete-token", refresh_token: "fixture", token_type: "bearer", expires_at: now.getTime() / 1000 + 86400,
    user: { id: profile.profile.athlete_id, email: "fixture@example.com", aud: "authenticated", role: "authenticated", app_metadata: {}, user_metadata: {} },
  })]);
  const writes: Record<string, unknown>[] = [];
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/me") return route.fulfill({ json: profile });
    if (path === "/api/today") return route.fulfill({ json: view });
    if (path === "/api/today/injury-checkin") {
      writes.push(route.request().postDataJSON());
      if (writes.length === 1) return route.fulfill({ status: 500, json: { detail: "Could not save test injury" } });
      return route.fulfill({ json: { open_injuries: view.open_injuries } });
    }
    if (path === `/api/plans/${view.active_plan.id}`) return route.fulfill({ json: {
      plan_id: view.active_plan.id, status: "ready", outputs: { structured_plan: { weeks: [{ week_index: 1, phase_label: "GPP",
        days: [{ date: view.today.training_day, weekday: "Mon", sessions: [view.live_prescription.session] }] }] } },
    } });
    return route.fulfill({ json: path === "/api/training/history" ? { sessions: [] } : path === "/api/plans" ? [] : {} });
  });
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/today");
  await expect(page).toHaveTitle(/UNLXCK/);
  const trigger = page.getByRole("button", { name: "+ Add another injury", exact: true });
  await trigger.click();
  const sheet = page.getByRole("dialog", { name: "Add another injury", exact: true });
  await expect(sheet).toBeVisible();
  return { sheet, trigger, writes, errors };
}

async function shot(page: Page, name: string) {
  if (!process.env.INJURY_SCREENSHOTS) return;
  mkdirSync(process.env.INJURY_SCREENSHOTS, { recursive: true });
  await page.screenshot({ path: `${process.env.INJURY_SCREENSHOTS}/${name}.png`, animations: "disabled" });
}

for (const [width, height] of [[320, 568], [375, 667], [390, 844], [430, 932], [1280, 800]]) {
  test(`injury location, impact, retry and dismissal at ${width}px`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height });
    const { sheet, trigger, writes, errors } = await setup(page, baseURL!);
    await expect(sheet.getByText("1. Where is the injury?")).toBeVisible();
    await expect(sheet.getByRole("group", { name: "Type", exact: true })).toHaveCount(0);
    await expect(sheet.getByRole("slider")).toHaveCount(0);
    await shot(page, `location-${width}`);
    await sheet.locator('[aria-label="Left shoulder"]:visible').first().tap();
    await expect(sheet.locator(".body-map-panel")).toBeHidden();
    await expect(sheet.getByText("2. Describe the injury")).toBeVisible();
    const slider = sheet.getByRole("slider", { name: "Impact on training" });
    await expect(slider).toHaveAttribute("aria-valuetext", "Not set");
    await sheet.getByRole("button", { name: "Soreness", exact: true }).tap();
    await sheet.getByRole("button", { name: "Save injury", exact: true }).tap();
    await expect(sheet.getByRole("alert")).toContainText("affecting your training");
    expect(writes).toHaveLength(0);
    for (const [index, label] of ["Not limiting me", "Limiting me", "Can’t train normally"].entries()) {
      const box = await slider.boundingBox();
      await page.touchscreen.tap(box!.x + box!.width * (index + 0.5) / 3, box!.y + box!.height / 2);
      await expect(slider).toHaveAttribute("aria-valuetext", label);
    }
    await slider.focus();
    await page.keyboard.press("Home");
    await expect(slider).toHaveAttribute("aria-valuetext", "Not limiting me");
    await page.keyboard.press("ArrowRight");
    await expect(slider).toHaveAttribute("aria-valuetext", "Limiting me");
    await page.keyboard.press("End");
    await expect(slider).toHaveAttribute("aria-valuetext", "Can’t train normally");
    await sheet.getByRole("button", { name: "Change", exact: true }).click();
    await expect(sheet.getByRole("slider")).toHaveCount(0);
    await sheet.getByRole("button", { name: "Keep Left shoulder", exact: true }).click();
    await expect(slider).toHaveAttribute("aria-valuetext", "Can’t train normally");
    await expect(sheet.getByRole("button", { name: "Soreness", exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect(sheet.locator(".today-injury-detail")).toHaveCount(0);
    for (const label of await sheet.locator(".level-slider-segment").all()) {
      expect(await label.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
      expect(await label.evaluate(el => getComputedStyle(el).whiteSpace)).toBe("nowrap");
    }
    expect((await new AxeBuilder({ page }).include(".today-injury-add-sheet").withRules([
      "aria-allowed-attr", "aria-input-field-name", "aria-required-attr", "aria-valid-attr-value", "label", "nested-interactive",
    ]).analyze()).violations).toEqual([]);
    await shot(page, `describe-${width}`);
    await sheet.getByRole("button", { name: "Save injury", exact: true }).click();
    await expect(page.getByText("Could not save test injury", { exact: true })).toBeVisible();
    await expect(slider).toHaveAttribute("aria-valuetext", "Can’t train normally");
    await sheet.getByRole("button", { name: "Save injury", exact: true }).click();
    await expect(sheet).toHaveCount(0);
    expect(writes[1]).toEqual({ injuries: [{ body_area: "Left shoulder", description: "soreness [training_impact:cant_train]", severity: "severe", status: "ongoing" }] });
    await trigger.click();
    await expect(sheet.getByRole("slider")).toHaveCount(0);
    await page.keyboard.press("Escape");
    await expect(sheet).toHaveCount(0);
    await expect(trigger).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });
}

test("iPhone safe areas, scrolling and visual keyboard viewport keep header reachable", async ({ page, baseURL }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setSafeAreaInsetsOverride", { insets: { top: 47, bottom: 34, left: 0, right: 0 } });
  const { sheet } = await setup(page, baseURL!);
  const close = sheet.getByRole("button", { name: "Close", exact: true });
  expect((await sheet.boundingBox())!.y).toBeGreaterThanOrEqual(47);
  await sheet.locator("form").evaluate(el => { el.scrollTop = el.scrollHeight; });
  await expect(close).toBeInViewport({ ratio: 1 });
  await shot(page, "iphone-scrolled-map");
  await sheet.getByRole("button", { name: "Can’t find the area? Enter it manually", exact: true }).click();
  await sheet.getByRole("textbox", { name: "Affected area" }).fill("Left shin");
  await sheet.getByRole("button", { name: "Use location", exact: true }).click();
  await sheet.getByRole("button", { name: "+ Add note (optional)", exact: true }).click();
  await sheet.getByRole("textbox", { name: "Note (optional)" }).fill("Only after running");
  // A keyboard-sized visual viewport plus browser panning, independent of the
  // layout viewport. Real iOS soft-keyboard behavior still needs device QA.
  await page.evaluate(() => {
    const viewport = window.visualViewport!;
    Object.defineProperty(viewport, "height", { configurable: true, value: 400 });
    Object.defineProperty(viewport, "offsetTop", { configurable: true, value: 80 });
    viewport.dispatchEvent(new Event("resize"));
    viewport.dispatchEvent(new Event("scroll"));
  });
  const box = (await sheet.boundingBox())!;
  expect(box.y).toBeGreaterThanOrEqual(127);
  expect(box.y + box.height).toBeLessThanOrEqual(446);
  await sheet.getByRole("button", { name: "Save injury", exact: true }).scrollIntoViewIfNeeded();
  await expect(close).toBeInViewport({ ratio: 1 });
  await expect(sheet.getByRole("button", { name: "Save injury", exact: true })).toBeInViewport({ ratio: 1 });
  await shot(page, "iphone-keyboard-viewport");
  await close.click();
  await expect(sheet).toHaveCount(0);
  expect(await page.locator("body").evaluate(el => el.style.position)).not.toBe("fixed");
});
