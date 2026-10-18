import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { isolateFromNetwork } from "./support";
import type { TrainingHistorySession } from "../lib/training-history";

async function setup(page: Page, baseURL: string, options: { path?: string | null; failSave?: boolean; failMe?: boolean; failToday?: boolean; terms?: boolean; plan?: boolean; consent?: boolean; rejectConsent?: boolean; failConsent?: boolean; manualHistory?: TrainingHistorySession[]; sharedHistory?: TrainingHistorySession[] } = {}) {
  await isolateFromNetwork(page, baseURL);
  const storageKey = `sb-${new URL(process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://stub.supabase.co").hostname.split(".")[0]}-auth-token`;
  await page.addInitScript(([key, value]) => localStorage.setItem(key, value), [storageKey, JSON.stringify({
    access_token: "tracking-test-token", refresh_token: "test-refresh", token_type: "bearer",
    expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
    user: { id: "athlete-1", email: "fighter@example.com", aud: "authenticated", role: "authenticated", app_metadata: {}, user_metadata: {} },
  })]);
  let path = options.path ?? null;
  let healthConsent = options.consent !== false;
  let consentFailed = false;
  let failed = false;
  let sessions: Record<string, unknown>[] = options.sharedHistory ?? [];
  let manualSessions: Record<string, unknown>[] = options.manualHistory ?? [];
  const writes: Record<string, unknown>[] = [];
  await page.route("**/api/**", async route => {
    const request = route.request();
    const endpoint = new URL(request.url()).pathname;
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (endpoint === "/api/me" || endpoint === "/api/me/compliance") {
      if (options.failMe) return json({ detail: "Unavailable" }, 503);
      if (endpoint === "/api/me/compliance") {
        writes.push(request.postDataJSON());
        if (options.failConsent && !consentFailed) { consentFailed = true; return json({ detail: "Unavailable" }, 503); }
        healthConsent = request.postDataJSON().health_data_consent === true;
      }
      if (request.method() === "PUT") {
        const body = request.postDataJSON(); writes.push(body);
        if (options.failSave && !failed) { failed = true; return json({ detail: "Unavailable" }, 503); }
        path = body.starting_path;
      }
      return json({ profile: { starting_path: path, athlete_id: "athlete-1", email: "fighter@example.com", full_name: "Alex", role: "athlete", access_status: "approved",
        technical_style: ["boxing"], tactical_style: [], stance: "orthodox", professional_status: "amateur", record: "",
        athlete_timezone: "Europe/London", athlete_locale: "en", appearance_mode: "dark", nutrition_profile: {},
        date_of_birth: "1995-01-01", meets_minimum_age: true, is_minor: false, terms_accepted: options.terms !== false, health_consent_granted: healthConsent,
        training_habits: options.manualHistory ? { enabled: true, decisions: [] } : undefined,
      }, plan_count: options.plan ? 1 : 0, latest_plan: options.plan ? { plan_id: "plan-9", status: "ready" } : null, latest_intake: null, username_rate_limit: {} });
    }
    if (endpoint === "/api/today") return options.failToday ? json({ detail: "Unavailable" }, 503) : json({
      active_plan: {}, today: { training_day: "2026-10-18", recommendation_state: "not_checked_in", decision_tier: "not_checked_in", warnings: [], next_session: {}, completion_status: "not_started", session_scope: "none" },
      open_injuries: [], risk_watch: [], week_summary: {}, quick_actions: [],
    });
    if (endpoint === "/api/training/history") return json({ sessions: new URL(request.url()).searchParams.get("manual_only") === "true" ? manualSessions : sessions });
    if (endpoint === "/api/training/sessions" && request.method() === "POST") {
      const body = request.postDataJSON(); writes.push(body);
      if (!healthConsent || options.rejectConsent) return json({ detail: { code: "health_data_consent_required", message: "Health-data consent is required." } }, 403);
      const row = { ...body, id: `manual-${sessions.length}`, source: "external", training_day: "2026-10-18", title: "Boxing", status: "done", plan_id: null };
      sessions = [row, ...sessions]; manualSessions = [row, ...manualSessions]; return json(row, 201);
    }
    if (endpoint === "/api/plans/active") return json({ detail: "No active plan" }, 404);
    if (endpoint === "/api/plans") return json([]);
    return json({ notifications: [], unread_count: 0, level: 1, total_xp: 0 });
  });
  return writes;
}

test("tracking keeps consent optional and grants it in one explicit tap inside the logger", async ({ page, baseURL }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const writes = await setup(page, baseURL!, { consent: false });
  await page.goto("/get-started");
  await page.getByRole("button", { name: /I already have a coach/ }).click();
  await expect(page).toHaveURL(/\/today$/);
  await page.getByRole("button", { name: "Log Training", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("Training logs include health-related information");
  await expect(dialog.getByRole("form")).toHaveCount(0);
  const allow = dialog.getByRole("button", { name: "Allow health-data use and continue", exact: true });
  await expect(allow).toBeFocused();
  expect(writes).toEqual([{ starting_path: "tracking_first" }]);
  expect((await new AxeBuilder({ page }).include("dialog").analyze()).violations).toEqual([]);
  await page.screenshot({ path: test.info().outputPath("contextual-consent.png") });
  await allow.click();
  await expect(page).toHaveURL(/\/today$/);
  await expect(page.getByRole("form", { name: "Log Training", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Boxing", exact: true })).toBeFocused();
  expect(writes).toEqual([{ starting_path: "tracking_first" }, { health_data_consent: true }]);
});

test("declining contextual consent keeps tracking and the round timer available", async ({ page, baseURL }) => {
  const writes = await setup(page, baseURL!, { consent: false, path: "tracking_first" });
  await page.goto("/today");
  await page.getByRole("button", { name: "Log Training", exact: true }).click();
  await page.getByRole("button", { name: "Not now", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("link", { name: /Round timer Start a session/ })).toBeVisible();
  expect(writes).toEqual([]);
});

test("failed contextual consent remains optional and can be retried", async ({ page, baseURL }) => {
  const writes = await setup(page, baseURL!, { consent: false, path: "tracking_first", failConsent: true });
  await page.goto("/today");
  await page.getByRole("button", { name: "Log Training", exact: true }).click();
  const allow = page.getByRole("button", { name: "Allow health-data use and continue", exact: true });
  await allow.click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("could not be saved");
  await expect(page.getByRole("form", { name: "Log Training", exact: true })).toHaveCount(0);
  await allow.click();
  await expect(page.getByRole("form", { name: "Log Training", exact: true })).toBeVisible();
  expect(writes).toEqual([{ health_data_consent: true }, { health_data_consent: true }]);
});

test("server-side consent withdrawal replaces the logger with a recovery route", async ({ page, baseURL }) => {
  await setup(page, baseURL!, { path: "tracking_first", rejectConsent: true });
  await page.goto("/today");
  await page.getByRole("button", { name: "Log Training", exact: true }).click();
  const form = page.getByRole("form", { name: "Log Training", exact: true });
  await form.getByRole("button", { name: "Boxing", exact: true }).click();
  await form.getByRole("button", { name: "45", exact: true }).click();
  await form.getByRole("button", { name: "Moderate", exact: true }).click();
  await form.getByRole("button", { name: "Save Session", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("button", { name: "Allow health-data use and continue", exact: true })).toBeVisible();
  await expect(form).toHaveCount(0);
});

for (const failedSource of ["none", "manual", "shared"]) {
  test(`habits use manual-only evidence independently of shared history (${failedSource})`, async ({ page, baseURL }) => {
    await page.clock.setFixedTime(new Date("2026-10-18T12:00:00Z"));
    const manual: TrainingHistorySession[] = ["2026-10-11", "2026-10-04"].map(day => ({
      id: day, source: "external", training_day: day, status: "done", title: "Boxing", activity: "boxing", duration_minutes: 45, effort: "moderate", plan_id: null,
    }));
    const prescribed: TrainingHistorySession[] = Array.from({ length: 30 }, (_, index) => ({
      id: `plan-${index}`, source: "unlxck", training_day: "2026-10-18", status: "done", title: "Prescribed strength", activity: null, duration_minutes: null, effort: null, plan_id: "old-plan",
    }));
    await setup(page, baseURL!, { path: "tracking_first", manualHistory: manual, sharedHistory: prescribed });
    const urls: string[] = [];
    page.on("request", request => { if (request.url().includes("/api/training/history")) urls.push(request.url()); });
    if (failedSource !== "none") await page.route(failedSource === "manual" ? "**/api/training/history?manual_only=true&limit=200" : "**/api/training/history", route => route.fulfill({ status: 503, contentType: "application/json", body: '{}' }));
    await page.goto("/today");
    await expect.poll(() => urls.some(url => url.endsWith("manual_only=true&limit=200"))).toBe(true);
    if (failedSource === "manual") {
      await page.getByText("Training habits", { exact: true }).click();
      await expect(page.getByText("History unavailable.", { exact: true })).toBeVisible();
      await expect(page.getByText("Boxing every Sunday?", { exact: true })).toHaveCount(0);
    } else await expect(page.getByText("Boxing every Sunday?", { exact: true })).toBeVisible();
    if (failedSource === "shared") await expect(page.getByText("Couldn’t load your training history.", { exact: true })).toBeVisible();
    else await expect(page.getByRole("region", { name: "Training history", exact: true })).toContainText("Prescribed strength");
  });
}

for (const width of [320, 390, 1280]) {
  test(`Tracking choice, log, repeat and plan later (${width}px)`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height: 844 });
    const errors: string[] = []; page.on("pageerror", e => errors.push(e.message));
    const writes = await setup(page, baseURL!);
    await page.goto("/get-started");
    await expect(page.getByRole("heading", { name: "How would you like to start?" })).toBeVisible();
    const tracking = page.getByRole("button", { name: /I already have a coach/ });
    await tracking.focus(); await expect(tracking).toBeFocused();
    expect((await new AxeBuilder({ page }).include("main").analyze()).violations).toEqual([]);
    await page.screenshot({ path: test.info().outputPath(`choice-${width}.png`) });
    await tracking.press("Enter");
    await expect(page).toHaveURL(/\/today$/);
    await expect(page.getByText("No training logged yet", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: /Round timer Start a session/ })).toBeVisible();
    await expect(page.getByText("Want extra S&C?", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Log Training", exact: true }).click();
    const form = page.getByRole("form", { name: "Log Training", exact: true });
    await form.getByRole("button", { name: "Boxing", exact: true }).click();
    await form.getByRole("button", { name: "45", exact: true }).click();
    await form.getByRole("button", { name: "Moderate", exact: true }).click();
    await form.getByRole("button", { name: "Save Session", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Log Training", exact: true })).toBeFocused();
    await expect(page.getByRole("button", { name: "Repeat last session", exact: true })).toBeVisible();
    await expect(page.locator("#tracking-history-heading").locator("..").locator("..")).toContainText("Boxing");
    await page.reload();
    await expect(page.getByText("Your training, your record.", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Repeat last session", exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect((await new AxeBuilder({ page }).include("main").analyze()).violations).toEqual([]);
    await page.screenshot({ path: test.info().outputPath(`tracking-${width}.png`) });
    await page.goto("/");
    await expect(page.getByText("Your training, your record.", { exact: true })).toBeVisible();
    await page.getByRole("link", { name: /Want extra S&C/ }).click();
    await expect(page).toHaveURL(/\/quick-build$/);
    expect(writes[0]).toEqual({ starting_path: "tracking_first" });
    expect(writes[1]).toMatchObject({ activity: "boxing", duration_minutes: 45, effort: "moderate" });
    expect(writes[1]).not.toHaveProperty("plan_id");
    expect(errors).toEqual([]);
  });
}

test("Saving failure stays on choice and retry saves plan-first", async ({ page, baseURL }) => {
  const writes = await setup(page, baseURL!, { failSave: true });
  await page.goto("/get-started");
  const plan = page.getByRole("button", { name: /Build my training plan/ });
  await plan.click(); await expect(page.getByRole("alert").filter({ hasText: "could not be saved" })).toBeVisible();
  await expect(page).toHaveURL(/\/get-started$/); await expect(plan).toBeEnabled();
  await plan.click(); await expect(page).toHaveURL(/\/quick-build$/);
  expect(writes).toEqual([{ starting_path: "plan_first" }, { starting_path: "plan_first" }]);
});

test("Unaccepted terms precede the choice", async ({ page, baseURL }) => {
  await setup(page, baseURL!, { terms: false }); await page.goto("/get-started");
  await expect(page).toHaveURL(/\/consent$/);
  await expect(page.getByRole("button", { name: /I already have a coach/ })).toHaveCount(0);
});

test("Existing athlete with a plan keeps their destination", async ({ page, baseURL }) => {
  await setup(page, baseURL!, { path: "tracking_first", plan: true }); await page.goto("/get-started");
  await expect(page).toHaveURL(/\/plans\/plan-9$/);
});

test("Profile failure never becomes first-use onboarding", async ({ page, baseURL }) => {
  await setup(page, baseURL!, { failMe: true }); await page.goto("/get-started");
  await expect(page.getByRole("heading", { name: "Couldn’t load your account" })).toBeVisible();
  await expect(page.getByRole("button", { name: /I already have a coach/ })).toHaveCount(0);
});

test("Today failure never becomes a no-plan empty state", async ({ page, baseURL }) => {
  await setup(page, baseURL!, { path: "tracking_first", failToday: true }); await page.goto("/today");
  await expect(page.getByRole("heading", { name: "Today is temporarily unavailable" })).toBeVisible();
  await expect(page.getByText("No training logged yet", { exact: true })).toHaveCount(0);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Today is temporarily unavailable" })).toBeVisible();
  await expect(page.getByText("Build your fight camp in minutes.", { exact: true })).toHaveCount(0);
});
