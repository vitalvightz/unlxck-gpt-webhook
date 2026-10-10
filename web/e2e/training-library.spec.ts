import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { isolateFromNetwork } from "./support";
import type { LibraryEntry } from "../lib/api-schema.generated";

const athlete = "00000000-0000-4000-8000-000000000001";
const storageKey = `sb-${new URL(process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://stub.supabase.co").hostname.split(".")[0]}-auth-token`;
const entry = (name: string, equipment: string[] | null, overrides: Partial<LibraryEntry> = {}): LibraryEntry => ({
  catalogue_id: name, name, equipment, equipment_state: equipment === null ? "absent" : "known", content_type: "strength_power",
  category: "training", context: "Strength", focus: ["Punching power"], discovery_match: null, exercise_key: null, media: null,
  selection_boundary: "training_validation_required", prescription_allowed: false, ...overrides,
});
const drills = [entry("Medicine Ball Hook Throw", ["medicine_ball"]), entry("Standing Cable Punch Simulation", ["cable"]),
  entry("Max-Power Bag Burst", ["heavy_bag"]), entry("Straight-Shot Re-Angle", ["punching_bag"])];
const rehab = entry("Banded Heel Push with Hold", ["band"], { category: "rehab", content_type: "rehabilitation", context: "Rehab · Achilles · Pain", selection_boundary: "rehab_pathway_only" });
const learn = entry("Pressure → Reset", null, { category: "learn", content_type: "visualisation", context: "Visualisation · Boxing · Brawler", selection_boundary: "excluded" });

async function setup(page: Page, baseURL: string) {
  await isolateFromNetwork(page, baseURL);
  // Isolation deliberately blocks the Google Fonts import; serve an empty
  // stylesheet so expected fallback typography does not emit a network error.
  await page.route("https://fonts.googleapis.com/**", route => route.fulfill({ contentType: "text/css", body: "" }));
  await page.addInitScript(([key, value]) => localStorage.setItem(key, value), [storageKey, JSON.stringify({
    access_token: "athlete-token", refresh_token: "test-refresh", token_type: "bearer", expires_in: 86400,
    expires_at: Math.floor(Date.now() / 1000) + 86400,
    user: { id: athlete, email: "fighter@example.com", aud: "authenticated", role: "authenticated", app_metadata: {}, user_metadata: {} },
  })]);
  let failSearch = false;
  const calls: string[] = [];
  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (url.pathname.startsWith("/api/training/library")) {
      expect(request.method()).toBe("GET");
      expect(request.headers().authorization).toBe("Bearer athlete-token");
      calls.push(url.search);
      if (failSearch && !url.pathname.endsWith("/entry")) return json({ detail: "Training library is temporarily unavailable." }, 503);
      // Optional live API lets the same flow exercise the real 2,855-row search
      // in local integration QA. CI retains the existing isolated web workflow.
      if (process.env.LIBRARY_TEST_API) {
        const response = await page.request.get(`${process.env.LIBRARY_TEST_API}${url.pathname}${url.search}`, { headers: { Authorization: "Bearer athlete-token" } });
        return route.fulfill({ response });
      }
      if (url.pathname.endsWith("/featured")) return json({ entry: null });
      if (url.pathname.endsWith("/entry")) {
        const selected = [...drills, rehab, learn].find(row => row.catalogue_id === url.searchParams.get("catalogue_id"))!;
        return json({ ...selected, source: "source.json", source_revision: "test", row_revision: "test",
          guidance: selected.category === "learn" ? { Instructions: ["Picture getting caught while entering."], Why: ["Rehearse restarting pressure from position."] } : {} });
      }
      const category = url.searchParams.get("category") ?? "training";
      const q = url.searchParams.get("q") ?? "";
      const gear = url.searchParams.get("equipment");
      const rows = category === "training" ? drills : category === "rehab" ? [rehab] : [learn];
      const normalize = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
      const entries = rows.filter(row => (!gear || row.equipment?.includes(gear)) && (!q || q === "punching power" || normalize(row.name).includes(normalize(q))));
      const values = (list: string[]) => list.map(value => ({ value, label: value.replaceAll("_", " "), count: 1 }));
      return json({ entries, total: entries.length, catalogue_total: 2855, offset: 0, limit: 24, next_offset: null, revision: "test",
        facets: { type: values(["strength_power"]), goal: values(["Punching power"]), sport: [], equipment: values(q ? ["medicine_ball", "cable", "heavy_bag", "punching_bag"] : ["medicine_ball", "barbell", "agility_ladder"]), body_focus: [] } });
    }
    if (url.pathname === "/api/me") return json({ profile: {
      athlete_id: athlete, email: "fighter@example.com", full_name: "Carlos", role: "athlete", access_status: "approved",
      technical_style: ["boxing"], tactical_style: [], stance: "orthodox", professional_status: "professional", record: "",
      athlete_timezone: "Europe/London", athlete_locale: "en", appearance_mode: "dark", nutrition_profile: {},
      date_of_birth: "1995-01-01", meets_minimum_age: true, is_minor: false, terms_accepted: true,
      health_consent_granted: true, private_trial_ack_at: "2026-01-01T12:00:00Z",
    }, plan_count: 0, latest_plan: null, latest_intake: null, username_rate_limit: {} });
    if (url.pathname === "/api/plans/active") return json({ detail: "No active plan" }, 404);
    if (url.pathname === "/api/plans") return json([]);
    if (url.pathname === "/api/training/history") return json({ sessions: [] });
    return json({ notifications: [], unread_count: 0, level: 1, total_xp: 0 });
  });
  return { calls, fail: (value: boolean) => { failSearch = value; } };
}

for (const width of [390, 1280]) {
  test(`Plan actions and featured curated demo (${width}px)`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height: 844 });
    await setup(page, baseURL!);
    const media = { video_id: "9dWwmyZ1Wng", start_s: 18, end_s: 24, source: "curated", channel_title: "Free Fitness Videos", orientation: "landscape" };
    await page.route("**/api/training/library/featured", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({ entry: { ...drills[0], media } }) }));
    // External services are isolated in CI. Thumbnail identity and the actual
    // native player are checked here; live thumbnail/playback get separate QA.
    await page.route("https://i.ytimg.com/**", route => route.fulfill({ status: 204, body: "" }));
    await page.goto("/plan");
    const log = page.getByRole("button", { name: "Log Training", exact: true });
    const find = page.getByRole("link", { name: "Find a Drill", exact: true });
    const logBox = (await log.boundingBox())!;
    const findBox = (await find.boundingBox())!;
    expect(Math.abs(logBox.y - findBox.y)).toBeLessThan(2);
    expect(Math.abs(logBox.width - findBox.width)).toBeLessThan(2);
    expect(Math.abs(logBox.height - findBox.height)).toBeLessThan(2);
    await log.click();
    await expect(page.getByRole("dialog", { name: "Log Training", exact: true })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(log).toBeFocused();
    const profile = page.getByRole("button", { name: /^Athlete profile:/ });
    await profile.click();
    await expect(page.getByRole("link", { name: "Edit profile & photo" })).toHaveAttribute("href", "/profile");
    await page.keyboard.press("Escape");
    const featured = page.getByRole("region", { name: "Featured drill", exact: true });
    await expect(featured).toContainText("Editor’s pick");
    const featuredBox = (await featured.boundingBox())!;
    const mainBox = (await page.getByRole("main").boundingBox())!;
    expect(Math.abs(featuredBox.x + featuredBox.width / 2 - mainBox.x - mainBox.width / 2)).toBeLessThan(2);
    await expect(featured.getByRole("button", { name: "Play Medicine Ball Hook Throw demo" })).toBeVisible();
    await expect(featured.getByRole("link", { name: "Watch on YouTube" })).toHaveAttribute("href", "https://www.youtube.com/watch?v=9dWwmyZ1Wng&t=18s");
    await featured.getByRole("button", { name: /^Medicine Ball Hook Throw/ }).click();
    await expect(page.getByRole("dialog", { name: "Medicine Ball Hook Throw", exact: true })).toContainText("Discovery only");
    await page.keyboard.press("Escape");
    expect((await new AxeBuilder({ page }).include('main').analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

for (const width of [320, 390, 1280, 1440]) {
  test(`Find a Drill without an active plan: search, filter, preview (${width}px)`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height: 844 });
    const errors: string[] = [];
    const consoleErrors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("console", message => {
      // A deliberate no-active-plan 404 is handled by Plan's empty state.
      if (message.type() === "error" && !message.location().url.includes("/api/plans/active")) consoleErrors.push(`${message.location().url}: ${message.text()}`);
    });
    const { calls } = await setup(page, baseURL!);
    await page.goto("/plan");
    const libraryLink = page.getByRole("link", { name: "Find a Drill", exact: true });
    await expect(libraryLink).toBeInViewport();
    expect((await libraryLink.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    await page.screenshot({ path: test.info().outputPath(`plan-library-entry-${width}.png`), fullPage: false, animations: "disabled" });
    await libraryLink.click();
    await expect(page).toHaveURL(/\/plans\/library$/);
    await expect(page.getByRole("heading", { name: "Find a Drill" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Training", exact: true })).toHaveAttribute("aria-pressed", "true");
    const categories = page.getByRole("group", { name: "Library category" });
    const tabWidths = await categories.getByRole("button").evaluateAll(buttons => buttons.map(button => button.getBoundingClientRect().width));
    expect(Math.max(...tabWidths) - Math.min(...tabWidths)).toBeLessThan(2);
    const tabBox = (await categories.boundingBox())!;
    const libraryBox = (await page.getByRole("region", { name: "Training library" }).boundingBox())!;
    expect(Math.abs(tabBox.width - libraryBox.width)).toBeLessThan(2);
    const search = page.getByRole("searchbox", { name: "Search drills" });
    await search.fill("punching power");
    const results = page.getByRole("list", { name: "Drill results" });
    if (process.env.LIBRARY_TEST_API) {
      await expect(results.locator("li")).not.toHaveCount(0);
      await expect(results).toContainText("Half-Kneeling Medicine-Ball Punch Throw");
      await expect(results).toContainText("Matches · Punch-specific power");
    } else {
      await expect(results.locator("li")).toHaveCount(4);
    }
    await expect(results.locator("li").first()).toContainText("Medicine Ball Hook Throw");
    expect((await search.boundingBox())!.width).toBeGreaterThanOrEqual(width < 390 ? 140 : 180);
    expect((await page.getByRole("button", { name: "Filters", exact: true }).boundingBox())!.width).toBeLessThan(160);
    await page.screenshot({ path: test.info().outputPath(`library-search-${width}.png`), fullPage: false, animations: "disabled" });
    await page.getByRole("button", { name: "Filters", exact: true }).click();
    const filters = page.getByRole("dialog", { name: "Filters", exact: true });
    await expect(filters.getByRole("combobox")).toHaveCount(5);
    await expect(filters).not.toContainText("Difficulty");
    await filters.getByRole("combobox", { name: "Equipment", exact: true }).selectOption("medicine_ball");
    await filters.getByRole("button", { name: "Show results" }).click();
    if (process.env.LIBRARY_TEST_API) {
      await expect(results).toContainText("Med Ball Chest Pass (Reactive)");
      await expect(results).toContainText("Related · Upper-body power");
    } else {
      await expect(results.locator("li")).toHaveCount(1);
    }
    await page.screenshot({ path: test.info().outputPath(`library-${width}.png`), fullPage: false, animations: "disabled" });
    expect((await new AxeBuilder({ page }).include('[aria-label="Training library"]').analyze()).violations).toEqual([]);
    const drill = results.getByRole("button").first();
    await drill.focus(); await page.keyboard.press("Enter");
    const preview = page.getByRole("dialog", { name: "Medicine Ball Hook Throw", exact: true });
    await expect(preview).toContainText("Injury, phase, equipment and programming checks");
    await expect(preview).toContainText("Coaching guidance unavailable.");
    await page.screenshot({ path: test.info().outputPath(`preview-${width}.png`), fullPage: false, animations: "disabled" });
    await page.keyboard.press("Tab");
    await expect(preview.getByRole("button", { name: "Close drill preview" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(drill).toBeFocused();
    expect(calls.some(value => value.includes("sport="))).toBe(false);
    expect(errors).toEqual([]);
    expect(consoleErrors).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}

test("Categories, collapsed coaching, empty reset and unavailable retry", async ({ page, baseURL }) => {
  const controls = await setup(page, baseURL!);
  await page.goto("/plans/library");
  const search = page.getByRole("searchbox", { name: "Search drills" });
  await expect(page.getByRole("list", { name: "Drill results" })).toBeVisible();
  await page.getByRole("button", { name: "Filters", exact: true }).click();
  await page.getByRole("dialog").getByRole("combobox", { name: "Equipment", exact: true }).selectOption("agility_ladder");
  await page.getByRole("button", { name: "Show results" }).click();
  await search.fill("punching power");
  await expect(page.getByRole("heading", { name: "No drills found" })).toBeVisible();
  await page.getByRole("button", { name: "Reset search" }).click();
  await expect(search).toHaveValue("");
  await page.getByRole("button", { name: "Rehab", exact: true }).click();
  await expect(page.getByRole("list", { name: "Drill results" })).toContainText("Rehab");
  await expect(page.getByText("Rehab pathway only. Your current stage and clinical clearance still apply.")).toBeVisible();
  await page.getByRole("button", { name: "Learn", exact: true }).click();
  await search.fill("Pressure Reset");
  await page.getByRole("list", { name: "Drill results" }).getByRole("button").first().click();
  const preview = page.getByRole("dialog");
  await expect(preview).toContainText("These entries are not workout exercises.");
  await expect(preview.getByRole("heading", { name: "Why", exact: true })).toBeHidden();
  await preview.getByText("Coaching details", { exact: true }).click();
  await expect(preview.getByRole("heading", { name: "Why", exact: true })).toBeVisible();
  expect((await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations).toEqual([]);
  await page.keyboard.press("Escape");
  controls.fail(true);
  await search.fill("zzzxqv");
  await expect(page.getByRole("region", { name: "Training library" }).getByRole("alert")).toContainText("Training library is temporarily unavailable.");
  await expect(page.getByRole("list", { name: "Drill results" })).toHaveCount(0);
  controls.fail(false);
  await page.getByRole("button", { name: "Retry search" }).click();
  await expect(page.getByRole("heading", { name: "No drills found" })).toBeVisible();
});
