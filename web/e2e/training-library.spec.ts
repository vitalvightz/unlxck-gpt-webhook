import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { isolateFromNetwork } from "./support";
import type { LibraryEntry } from "../lib/api-schema.generated";
import canonicalFixture from "./fixtures/canonical-metadata-library.json";

const athlete = "00000000-0000-4000-8000-000000000001";
const storageKey = `sb-${new URL(process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://stub.supabase.co").hostname.split(".")[0]}-auth-token`;
const entry = (name: string, equipment: string[] | null, overrides: Partial<LibraryEntry> = {}): LibraryEntry => ({
  catalogue_id: name, name, equipment, equipment_state: equipment === null ? "absent" : "known", equipment_requirements: null, content_type: "strength_power",
  category: "training", context: "Strength", focus: ["Punching power"], verified_goals: ["Punching power"], exercise_details: [], discovery_match: null, exercise_key: null, media: null,
  selection_boundary: "training_validation_required", prescription_allowed: false, log_format: null, ...overrides,
});
const drills = [entry("Medicine Ball Hook Throw", ["medicine_ball"]), entry("Standing Cable Punch Simulation", ["cable"]),
  entry("Max-Power Bag Burst", ["heavy_bag"]), entry("Straight-Shot Re-Angle", ["punching_bag"])];
const rehab = entry("Banded Heel Push with Hold", ["band"], { category: "rehab", content_type: "rehabilitation", context: "Rehab · Achilles · Pain", selection_boundary: "rehab_pathway_only" });
const learn = entry("Pressure → Reset", null, { category: "learn", content_type: "visualisation", context: "Visualisation · Boxing · Brawler", selection_boundary: "excluded" });

async function chooseFilter(page: Page, field: string, value: string) {
  await page.getByRole("dialog").getByRole("button", { name: new RegExp(`^${field}: `) }).click();
  await page.getByRole("dialog").locator(`button[data-value="${value}"]`).click();
}

for (const width of [320, 390, 1280]) {
  test(`Reviewed canonical filters preserve independent selections (${width}px)`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height: 844 });
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
    await setup(page, baseURL!);
    await page.route("**/api/training/library**", async route => {
      const url = new URL(route.request().url());
      expect(route.request().method()).toBe("GET");
      expect(route.request().headers().authorization).toBe("Bearer athlete-token");
      if (process.env.LIBRARY_TEST_API) {
        const response = await page.request.get(`${process.env.LIBRARY_TEST_API}${url.pathname}${url.search}`, { headers: { Authorization: "Bearer athlete-token" } });
        return route.fulfill({ response });
      }
      const key = [...url.searchParams.entries()].filter(([key, value]) => ["equipment", "type", "body_focus"].includes(key) && value).sort().map(([key, value]) => `${key}=${value}`).join("&");
      const body = url.pathname.endsWith("/entry")
        ? canonicalFixture.previews[url.searchParams.get("catalogue_id")! as keyof typeof canonicalFixture.previews]
        : canonicalFixture.responses[key as keyof typeof canonicalFixture.responses];
      expect(body, `Backend-derived fixture exists for ${url.search}`).toBeTruthy();
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
    });
    await page.goto("/plans/library");
    await expect(page.getByRole("heading", { name: "Find a Drill", exact: true })).toBeVisible();
    const status = page.getByRole("region", { name: "Training library" }).getByRole("status");
    await expect(status).toHaveText("1,010 drills");
    const openFilters = async () => {
      await page.getByRole("button", { name: /^Filters/ }).click();
      const sheet = page.getByRole("dialog", { name: "Filters", exact: true });
      await sheet.getByText("Other filters", { exact: true }).click();
      return sheet;
    };
    let filters = await openFilters();
    await filters.getByRole("button", { name: /^Equipment: / }).click();
    const equipment = page.getByRole("group", { name: "Equipment options", exact: true });
    for (const [value, label] of [["battle_ropes", "Battle ropes (7)"], ["kettlebell", "Kettlebell (24)"], ["weight_vest", "Weight vest (6)"], ["rower", "Rower (8)"], ["double_end_bag", "Double-end bag (4)"]]) {
      await expect(equipment.locator(`button[data-value="${value}"]`)).toHaveCount(1);
      await expect(equipment.locator(`button[data-value="${value}"]`)).toHaveText(label.replace(" (", "").replace(")", "") + " ");
    }
    for (const value of ["battle_rope", "kettlebells", "weighted_vest", "rowing_machine", "double-end_bag"]) await expect(equipment.locator(`button[data-value="${value}"]`)).toHaveCount(0);
    await page.getByRole("button", { name: "← Back to filters", exact: true }).click();
    await filters.getByRole("button", { name: /^Body area: / }).click();
    await expect(page.getByRole("dialog").locator('button[data-value="adductors"]')).toHaveText("Inner thighs (adductors)7 ");
    await page.getByRole("button", { name: "← Back to filters", exact: true }).click();
    await page.screenshot({ path: test.info().outputPath(`canonical-filters-${width}.png`), animations: "disabled" });
    expect((await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await chooseFilter(page, "Equipment", "kettlebell");
    await expect(status).toHaveText("24 drills");
    await chooseFilter(page, "Training type", "strength_power");
    const combined = canonicalFixture.responses["equipment=kettlebell&type=strength_power"];
    await expect(status).toHaveText(`${combined.total} drills`);
    await filters.getByRole("button", { name: "Show results", exact: true }).click();
    filters = await openFilters();
    await expect(filters.getByRole("button", { name: /^Training type: / })).toHaveAccessibleName("Training type: Strength & power");
    await expect(filters.getByRole("button", { name: /^Equipment: / })).toHaveAccessibleName("Equipment: Kettlebell");
    await chooseFilter(page, "Equipment", "");
    await expect(filters.getByRole("button", { name: /^Training type: / })).toHaveAccessibleName("Training type: Strength & power");
    await chooseFilter(page, "Training type", "");
    await expect(status).toHaveText("1,010 drills");
    await chooseFilter(page, "Equipment", "battle_ropes");
    await expect(status).toHaveText("7 drills");
    await filters.getByRole("button", { name: "Show results", exact: true }).click();
    const results = page.getByRole("list", { name: "Drill results" });
    await expect(results).not.toContainText("Rope Climb");
    const drill = results.getByRole("button").first();
    await drill.focus(); await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog")).toContainText("Discovery only");
    await expect(page.getByRole("dialog").getByText("Loading drill…", { exact: true })).toBeHidden();
    await page.keyboard.press("Escape");
    await expect(drill).toBeFocused();
    await page.screenshot({ path: test.info().outputPath(`canonical-results-${width}.png`), animations: "disabled" });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });
}

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
          metadata_projection: [], guidance: selected.category === "learn" ? { Instructions: ["Picture getting caught while entering."], Why: ["Rehearse restarting pressure from position."] } : {} });
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

for (const width of [320, 390, 1280]) {
  test(`Reviewed equipment setup and unresolved requirements (${width}px)`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height: 844 });
    await setup(page, baseURL!);
    const makeRequirement = (mode: "ALL" | "UNKNOWN", items: string[]) => ({
      status: mode === "UNKNOWN" ? "unresolved" : "reviewed", groups: [{ mode, items: items.map(canonical_id => ({ canonical_id, kind: "apparatus", quantity: null })) }],
      source_value: mode === "ALL" ? "sledgehammer/tire" : "treadmill/rower", source: "exercise_bank.json", source_pointer: "/equipment",
      catalogue_id: "fixture", row_revision: "fixture", audit_decisions: ["MI-71931d8b6978"], evidence: "Reviewed source apparatus; mandatory target retained.",
    });
    const reviewed = { ...drills[0], catalogue_id: "exercise_bank.json:7731eda3-0acb-4c6d-b81f-c917bb0d2b62", name: "Rotational Sledgehammer Strike", equipment: ["sledgehammer", "tire"], equipment_requirements: makeRequirement("ALL", ["sledgehammer", "tire"]) };
    const unknown = { ...drills[0], catalogue_id: "exercise_bank.json:1c2ee7d5-21f5-4e40-bbc7-347a090d7413", name: "Tabata Sprints (Treadmill/Row)", equipment: ["treadmill/rower"], equipment_requirements: makeRequirement("UNKNOWN", []) };
    await page.route("**/api/training/library**", route => {
      const url = new URL(route.request().url());
      const selected = url.searchParams.get("catalogue_id") === unknown.catalogue_id ? unknown : reviewed;
      const entries = url.searchParams.get("equipment") ? [reviewed] : [reviewed, unknown];
      const body = url.pathname.endsWith("/entry") ? { ...selected, source: "exercise_bank.json", source_revision: "fixture", row_revision: "fixture", guidance: {}, metadata_projection: [] }
        : { entries, total: entries.length, catalogue_total: 2855, offset: 0, limit: 24, next_offset: null, revision: "fixture",
          facets: { type: [], sport: [], goal: [], body_focus: [], equipment: [{ value: "sledgehammer", label: "Sledgehammer", count: 1 }] } };
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
    });
    await page.goto("/plans/library");
    const results = page.getByRole("list", { name: "Drill results" });
    await expect(results).toContainText("Requires: sledgehammer + tire");
    await expect(results).toContainText("Equipment setup needs review");
    await expect(results).not.toContainText("No equipment");
    await page.getByRole("button", { name: /^Filters/ }).click();
    const filters = page.getByRole("dialog", { name: "Filters", exact: true });
    await filters.getByText("Other filters", { exact: true }).click();
    await chooseFilter(page, "Equipment", "sledgehammer");
    await filters.getByRole("button", { name: "Show results", exact: true }).click();
    await expect(results).not.toContainText("Tabata Sprints");
    const drill = results.getByRole("button").first();
    await drill.click();
    const preview = page.getByRole("dialog", { name: reviewed.name, exact: true });
    await expect(preview.getByRole("heading", { name: "Equipment setup" })).toBeVisible();
    await expect(preview).toContainText("Requires: sledgehammer + tire");
    await expect(preview).toContainText("Discovery only");
    expect((await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: test.info().outputPath(`equipment-requirements-${width}.png`), animations: "disabled" });
    await page.keyboard.press("Escape");
    await expect(drill).toBeFocused();
  });
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
    await expect(page.getByRole("link", { name: "Edit profile & photo" })).toHaveAttribute("href", "/settings#account");
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
    await filters.getByText("Other filters", { exact: true }).click();
    await expect(filters.getByRole("combobox")).toHaveCount(0);
    await expect(filters.locator('button[aria-label*=": "]')).toHaveCount(9);
    await expect(filters).not.toContainText("Difficulty");
    await chooseFilter(page, "Equipment", "medicine_ball");
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
  await page.getByRole("dialog").getByText("Other filters", { exact: true }).click();
  await chooseFilter(page, "Equipment", "agility_ladder");
  await page.getByRole("button", { name: "Show results" }).click();
  await search.fill("punching power");
  await expect(page.getByRole("heading", { name: "No exercises match this search and these filters." })).toBeVisible();
  await page.getByRole("button", { name: "Clear all filters" }).click();
  await expect(search).toHaveValue("punching power");
  await expect(page.getByRole("list", { name: "Drill results" })).toBeVisible();
  await search.fill("");
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

test("Mobile Skill focus picker searches 22 choices and restores filter focus", async ({ page, baseURL }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page, baseURL!);
  const labels = ["Footwork", "Striking", "Grappling", "Defence", "Clinch work", "Angle exits", "Create angles", "Takedown defence", "Takedown entries", "Manage range", "Cut off the ring", "Ring positioning", "Cage positioning", "Set up counters", "Apply pressure", "Recover your base", "Scrambles & stand-ups", "Kicking & kick recovery", "Hand-foot timing", "Cue-response practice", "Stance transitions", "Decision practice"];
  await page.route("**/api/training/library**", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({
    entries: [drills[0]], total: 1, catalogue_total: 2855, offset: 0, limit: 24, next_offset: null, revision: "picker",
    facets: { skill_focus: labels.map((label, i) => ({ value: `skill_${i}`, label, count: 1 })) },
  }) }));
  await page.goto("/plans/library");
  await page.getByRole("button", { name: "Filters", exact: true }).click();
  await page.getByRole("button", { name: "Skill focus: Any", exact: true }).click();
  const picker = page.getByRole("dialog", { name: "Skill focus", exact: true });
  await expect(picker.locator('button[data-value]')).toHaveCount(23);
  await expect(picker.getByRole("button", { name: "← Back to filters", exact: true })).toBeFocused();
  await page.screenshot({ path: test.info().outputPath("skill-focus-picker-390.png"), animations: "disabled" });
  const search = picker.getByRole("searchbox", { name: "Search skill focus options" });
  await search.fill("takedown def");
  await expect(picker.locator('button[data-value]')).toHaveCount(2);
  await expect(picker.locator('button[data-value="skill_7"]')).toHaveText("Takedown defence1");
  expect((await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await picker.locator('button[data-value="skill_7"]').click();
  const filters = page.getByRole("dialog", { name: "Filters", exact: true });
  await expect(filters.getByRole("button", { name: "Skill focus: Takedown defence", exact: true })).toBeFocused();
  await filters.getByRole("button", { name: "Show results", exact: true }).click();
  await page.getByRole("button", { name: "Remove Skill focus filter", exact: true }).click();
  await expect(page.getByRole("button", { name: "Filters", exact: true })).toBeVisible();
});
