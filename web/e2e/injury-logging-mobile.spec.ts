import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdirSync } from "node:fs";
import fixtures from "./fixtures/rehab-today.json";
import { isolateFromNetwork } from "./support";

test.use({ hasTouch: true });

async function setup(page: Page, baseURL: string, longNames = false) {
  await isolateFromNetwork(page, baseURL);
  const { view, profile } = structuredClone(fixtures.chest);
  if (longNames) {
    view.open_injuries[0].label = "Left shoulder instability";
    view.open_injuries.push({ ...view.open_injuries[0], id: "second-injury", label: "Left ankle sprain" });
    Object.assign(view.live_prescription.session.blocks[0], {
      display_name: "Shoulder instability protective guidance", is_loading: false,
      drill_snapshot: { rehab_stage: "calm", function: "recovery_downregulation", dose: {} },
    });
  }
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

for (const width of [320, 390]) {
  test(`long rehab content stays within the session card at ${width}px`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height: 844 });
    const { sheet } = await setup(page, baseURL!, true);
    await sheet.getByRole("button", { name: "Close", exact: true }).click();
    await expect(sheet).toHaveCount(0);
    const card = page.locator(".today-session-card");
    await card.scrollIntoViewIfNeeded();
    await expect(card).not.toContainText("Today's rehab");
    await expect(card).not.toContainText("No rehab exercises");
    const cardBox = (await card.boundingBox())!;
    for (const selector of [".today-injury-strip", ".ex-row", ".today-injury-guidance", ".today-injury-guidance button"]) {
      const items = card.locator(selector);
      expect(await items.count()).toBeGreaterThan(0);
      for (const item of await items.all()) {
        const box = (await item.boundingBox())!;
        expect(box.x).toBeGreaterThanOrEqual(cardBox.x - 1);
        expect(box.x + box.width).toBeLessThanOrEqual(cardBox.x + cardBox.width + 1);
      }
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await shot(page, `rehab-long-${width}`);
  });
}

async function shot(page: Page, name: string) {
  if (!process.env.INJURY_SCREENSHOTS) return;
  mkdirSync(process.env.INJURY_SCREENSHOTS, { recursive: true });
  await page.screenshot({ path: `${process.env.INJURY_SCREENSHOTS}/${name}.png`, animations: "disabled" });
}

test("sheet backdrop does not fade its text and injury rows have no tap flash", async ({ page, baseURL }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const { sheet } = await setup(page, baseURL!);
  const backdrop = page.locator(".injury-sheet-backdrop");
  expect(await backdrop.evaluate(el => getComputedStyle(el).opacity)).toBe("1");
  await sheet.getByRole("button", { name: "Close", exact: true }).click();
  await expect(sheet).toHaveCount(0);
  const summary = page.locator(".today-injury-summary-row").first();
  expect(await summary.evaluate(el => getComputedStyle(el).webkitTapHighlightColor)).toBe("rgba(0, 0, 0, 0)");
  expect(await summary.evaluate(el => Boolean(el.closest(".today-injury-list")?.parentElement?.classList.contains("today-auto-height-inner")))).toBe(false);
  await summary.tap();
  await expect(summary).toHaveAttribute("aria-expanded", "true");
  await summary.tap();
  await expect(summary).toHaveAttribute("aria-expanded", "false");
});

test("expanded decision evidence reaches the rounded card edge", async ({ page, baseURL }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const { sheet } = await setup(page, baseURL!);
  await sheet.getByRole("button", { name: "Close", exact: true }).click();
  await expect(sheet).toHaveCount(0);
  const card = page.locator(".today-decision-banner[data-current-guidance]").first();
  const disclosure = card.locator(".today-decision-disclosure");
  if (await disclosure.getAttribute("open") === null) await disclosure.locator("summary").click();
  const evidence = card.locator(".today-decision-evidence");
  const cardBox = (await card.boundingBox())!;
  const evidenceBox = (await evidence.boundingBox())!;
  expect(Math.abs(cardBox.y + cardBox.height - evidenceBox.y - evidenceBox.height)).toBeLessThanOrEqual(2);
  await shot(page, "decision-evidence-390");
});

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
  await sheet.getByRole("textbox", { name: "Affected area" }).blur();
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
