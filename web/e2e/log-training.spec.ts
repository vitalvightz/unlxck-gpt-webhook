import { expect, test, type Locator, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { isolateFromNetwork } from "./support";
import type { TrainingHabitPreferences } from "../lib/training-habits";
import type { TrainingHistorySession } from "../lib/training-history";

const athlete = "00000000-0000-4000-8000-000000000001";
const token = "log-training-test-token";
const storageKey = `sb-${new URL(process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://stub.supabase.co").hostname.split(".")[0]}-auth-token`;
const prescribed: TrainingHistorySession = {
  id: "prescribed", source: "unlxck", title: "Strength & Power", status: "done", training_day: "2026-10-10",
  activity: null, duration_minutes: null, effort: null, plan_id: "prior-plan",
  session_rpe: 7, notes: "Coach session",
};

async function setup(page: Page, baseURL: string, lostResponse: boolean | "network" = false, failMutations = false, initialSessions: TrainingHistorySession[] = [prescribed], initialHabits: TrainingHabitPreferences = { enabled: true, decisions: [] }, trainingDay = "2026-10-18") {
  await isolateFromNetwork(page, baseURL);
  const testNow = new Date(`${trainingDay}T12:00:00Z`);
  await page.clock.setFixedTime(testNow);
  await page.addInitScript(([key, value]) => localStorage.setItem(key, value), [storageKey, JSON.stringify({
    access_token: token, refresh_token: "test-refresh", token_type: "bearer",
    expires_in: 86400, expires_at: Math.floor(testNow.getTime() / 1000) + 86400,
    user: { id: athlete, email: "fighter@example.com", aud: "authenticated", role: "authenticated", app_metadata: {}, user_metadata: {} },
  })]);
  let sessions = [...initialSessions];
  const created = new Map<string, TrainingHistorySession>();
  const submissions: Record<string, unknown>[] = [];
  let habits = initialHabits;
  let habitRevision = 0;
  let editAttempts = 0;
  let deleteAttempts = 0;
  await page.route("**/api/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/me" && request.method() === "PUT") {
      const body = request.postDataJSON();
      if (body.training_habits_revision !== habitRevision) return json({ detail: "Routines changed on another device. Refresh and try again." }, 409);
      habits = body.training_habits; habitRevision++;
    }
    if (path === "/api/me") return json({ profile: {
      training_habits: habits, training_habits_revision: habitRevision,
      athlete_id: athlete, email: "fighter@example.com", full_name: "Carlos", role: "athlete", access_status: "approved",
      technical_style: ["boxing"], tactical_style: [], stance: "orthodox", professional_status: "professional", record: "",
      athlete_timezone: "Europe/London", athlete_locale: "en", appearance_mode: "dark", nutrition_profile: {},
      date_of_birth: "1995-01-01", meets_minimum_age: true, is_minor: false, terms_accepted: true,
      health_consent_granted: true, private_trial_ack_at: "2026-01-01T12:00:00Z",
    }, plan_count: 0, latest_plan: null, latest_intake: null, username_rate_limit: {} });
    if (path === "/api/today") return json({
      active_plan: { id: "plan-1", name: "Camp", phase: "SPP" },
      today: { training_day: trainingDay, recommendation_state: "not_checked_in", decision_tier: "not_checked_in",
        warnings: [], next_session: {}, completion_status: "not_started", session_scope: "none", session_label: "No session" },
      open_injuries: [], risk_watch: [], week_summary: {}, quick_actions: [],
    });
    if (path === "/api/plans/plan-1") return json({ outputs: {} });
    if (path === "/api/plans/active") return json({ detail: "No active plan" }, 404);
    if (path === "/api/plans") return json([]);
    if (path === "/api/training/history") return json({ sessions });
    if (path === "/api/training/sessions" && request.method() === "POST") {
      expect(request.headers().authorization).toBe(`Bearer ${token}`);
      const body = request.postDataJSON();
      submissions.push(body);
      if (!created.has(body.client_request_id)) {
        const row: TrainingHistorySession = {
        id: `manual-${created.size}`, source: "external", training_day: body.training_day ?? trainingDay, status: "done",
        plan_id: null,
        title: body.activity.charAt(0).toUpperCase() + body.activity.slice(1), activity: body.activity, duration_minutes: body.duration_minutes, effort: body.effort,
      };
        created.set(body.client_request_id, row);
        sessions = [row, ...sessions];
      }
      if (lostResponse === "network" && submissions.length === 1) return route.abort("failed");
      if (lostResponse && submissions.length === 1) return json({ detail: "Saved, but response lost. Retry." }, 503);
      return json(created.get(body.client_request_id), 201);
    }
    if (path.startsWith("/api/training/sessions/") && request.method() === "PATCH") {
      const body = request.postDataJSON();
      editAttempts += 1;
      if (failMutations && editAttempts === 1) return route.fulfill({ status: 502, contentType: "text/html", body: "<html>Bad Gateway</html>" });
      sessions[0] = { ...sessions[0], ...body, title: "Boxing" };
      return json(sessions[0]);
    }
    if (path.startsWith("/api/training/sessions/") && request.method() === "DELETE") {
      deleteAttempts += 1;
      if (failMutations && deleteAttempts === 1) return route.fulfill({ status: 502, contentType: "text/html", body: "<html>Bad Gateway</html>" });
      sessions = sessions.filter(row => row.source !== "external");
      return route.fulfill({ status: 204 });
    }
    return json({ notifications: [], unread_count: 0, level: 1, total_xp: 0 });
  });
  return submissions;
}

async function choose(scope: Page | Locator, page: Page, field: string, option: string) {
  await scope.getByRole("combobox", { name: field, exact: true }).click();
  await expect(page.getByRole("listbox")).toBeVisible();
  await page.getByRole("option", { name: option, exact: true }).click();
  await expect(page.getByRole("listbox")).toHaveCount(0);
}

for (const width of [390, 1280]) {
  test(`Plan logs work; History edits and deletes it (${width}px)`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height: 844 });
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    const submissions = await setup(page, baseURL!, false, true);
    await page.goto("/plan");
    await page.getByRole("button", { name: "Log Training", exact: true }).click();
    const form = page.getByRole("form", { name: "Log Training", exact: true });
    await expect(form.getByRole("combobox")).toHaveCount(2);
    await expect(form.locator("input[required]")).toHaveCount(1);
    await expect(form.getByLabel("Training date (optional)")).toBeHidden();
    await form.getByRole("combobox", { name: "Activity", exact: true }).press("ArrowDown");
    await expect(page.getByRole("listbox")).toBeVisible();
    await expect(page.locator(".custom-select-menu-sheet")).toHaveCount(width === 390 ? 1 : 0);
    await page.screenshot({ path: test.info().outputPath("activity-picker.png") });
    await page.keyboard.press("Escape");
    await expect(page.getByRole("listbox")).toHaveCount(0);
    await expect(page.getByRole("dialog")).toBeVisible();
    await choose(form, page, "Activity", "Sparring");
    await form.getByLabel("Duration (minutes)").fill("60");
    await choose(form, page, "Effort", "Hard");
    // Compare rendered styling with the existing Plan CTA, catching unstyled
    // default buttons even if saving still works functionally.
    const ctaAppearance = (element: Element) => {
      const css = getComputedStyle(element);
      return [css.backgroundColor, css.backgroundImage, css.borderRadius, css.color];
    };
    expect(await form.getByRole("button", { name: "Save Session", exact: true }).evaluate(ctaAppearance))
      .toEqual(await page.getByRole("link", { name: "Quick Build Plan" }).evaluate(ctaAppearance));
    await page.screenshot({ path: test.info().outputPath("log-training-form.png") });
    expect((await new AxeBuilder({ page }).include('dialog').analyze()).violations).toEqual([]);
    await form.getByRole("button", { name: "Save Session", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByRole("region", { name: "Log Training", exact: true }).getByRole("status")).toContainText("logged successfully");
    await expect(page.locator(".history-list")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Edit Sparring" })).toHaveCount(0);
    expect(submissions[0]).toMatchObject({ activity: "sparring", duration_minutes: 60, effort: "hard" });
    expect(Object.keys(submissions[0]).sort()).toEqual(["activity", "client_request_id", "duration_minutes", "effort"]);
    await page.reload();
    await expect(page.getByRole("button", { name: "Edit Sparring" })).toHaveCount(0);
    if (width === 390) await page.getByRole("button", { name: "Open navigation" }).click();
    await page.getByRole("link", { name: /^History/ }).first().click();
    const history = page.locator(".history-list");
    await expect(history).toContainText("Sparring");
    await expect(history.getByRole("button", { name: "Edit Strength & Power" })).toHaveCount(0);
    const editButton = history.getByRole("button", { name: "Edit Sparring", exact: true });
    const deleteButton = history.getByRole("button", { name: "Delete Sparring", exact: true });
    const editBox = await editButton.boundingBox();
    const deleteBox = await deleteButton.boundingBox();
    expect(Math.abs(editBox!.y - deleteBox!.y)).toBeLessThanOrEqual(2);
    expect(editBox!.width).toBeLessThanOrEqual(44);
    expect(deleteBox!.width).toBeLessThan(120);
    expect(deleteBox!.x).toBeGreaterThan(editBox!.x);
    await page.screenshot({ path: test.info().outputPath("history-compact-controls.png") });
    expect((await new AxeBuilder({ page }).include(".history-list").analyze()).violations).toEqual([]);
    await editButton.click();
    await choose(page, page, "Activity", "Boxing");
    await page.getByLabel("Duration (minutes)").fill("45");
    await choose(page, page, "Effort", "Moderate");
    await page.getByRole("button", { name: "Save Session", exact: true }).click();
    await expect(history).toContainText("45 min");
    await expect(history).toContainText("Moderate");
    await page.goto("/history");
    await expect(page.locator(".history-list")).toContainText("Boxing");
    await expect(page.locator(".history-list")).toContainText("Added by you");
    await expect(page.locator(".history-list")).toContainText("45 min");
    await expect(page.locator(".history-list")).toContainText("RPE 7/10");
    await expect(page.locator(".history-list")).toContainText("Coach session");
    await expect(page.locator(".history-list > li")).toHaveCount(2);
    await page.getByRole("button", { name: "Delete Boxing", exact: true }).click();
    await expect(history.getByRole("listitem")).toHaveCount(1);
    await page.reload();
    await expect(history).not.toContainText("Boxing");
    await page.goto("/plan");
    await expect(page.locator(".history-list")).toHaveCount(0);
    await page.getByRole("button", { name: "Log Training", exact: true }).click();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Log Training", exact: true })).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });
}

test("retry after a lost save response keeps the same request ID", async ({ page, baseURL }) => {
  const submissions = await setup(page, baseURL!, true);
  await page.goto("/plans");
  await page.getByRole("button", { name: "Log Training", exact: true }).click();
  await choose(page, page, "Activity", "Sparring");
  await page.getByLabel("Duration (minutes)").fill("60");
  await choose(page, page, "Effort", "Hard");
  await page.getByRole("button", { name: "Save Session", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("response lost");
  await page.getByRole("button", { name: "Save Session", exact: true }).click();
  await expect(page.getByRole("region", { name: "Log Training", exact: true }).getByRole("status")).toContainText("logged successfully");
  expect(submissions).toHaveLength(2);
  expect(submissions[1].client_request_id).toBe(submissions[0].client_request_id);
});

test("log yesterday's sparring with the optional date and preserve it after editing", async ({ page, baseURL }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const submissions = await setup(page, baseURL!);
  await page.goto("/plans");
  await page.getByRole("button", { name: "Log Training", exact: true }).click();
  await choose(page, page, "Activity", "Sparring");
  await page.getByLabel("Duration (minutes)").fill("60");
  await choose(page, page, "Effort", "Hard");
  await page.getByText("Training date · Current day", { exact: true }).click();
  await page.getByLabel("Training date (optional)").fill("2026-10-09");
  await page.screenshot({ path: test.info().outputPath("backdated-training-form.png") });
  expect((await new AxeBuilder({ page }).include('dialog').analyze()).violations).toEqual([]);
  await page.getByRole("button", { name: "Save Session", exact: true }).click();
  expect(submissions[0]).toMatchObject({ activity: "sparring", duration_minutes: 60, effort: "hard", training_day: "2026-10-09" });
  await page.goto("/history");
  const history = page.locator(".history-list");
  await expect(history).toContainText("Fri 09 Oct 2026");
  await page.reload();
  await page.getByRole("button", { name: "Edit Sparring", exact: true }).click();
  await page.getByLabel("Duration (minutes)").fill("45");
  await page.getByRole("button", { name: "Save Session", exact: true }).click();
  await expect(history).toContainText("Fri 09 Oct 2026");
  await expect(history).toContainText("45 min");
  await expect(history).toContainText("Hard");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});


test("failed edits and deletes preserve the session and allow another attempt", async ({ page, baseURL }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page, baseURL!);
  await page.goto("/plans");
  await page.getByRole("button", { name: "Log Training", exact: true }).click();
  await choose(page, page, "Activity", "Sparring");
  await page.getByLabel("Duration (minutes)").fill("60");
  await choose(page, page, "Effort", "Hard");
  await page.getByRole("button", { name: "Save Session", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.goto("/history");
  let fail = true;
  const attempts: string[] = [];
  await page.route("**/api/training/sessions/*", async route => {
    attempts.push(route.request().method());
    if (fail && route.request().method() === "DELETE") return route.fulfill({ status: 502, contentType: "text/html", body: "<html>Bad Gateway</html>" });
    if (fail) return route.fulfill({ status: 403, contentType: "application/json", body: JSON.stringify({ detail: "Session could not be changed." }) });
    await route.fallback();
  });
  const history = page.locator(".history-list");
  await page.getByRole("button", { name: "Edit Sparring", exact: true }).click();
  await page.getByLabel("Duration (minutes)").fill("45");
  await page.getByRole("button", { name: "Save Session", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("Session could not be changed");
  await expect(page.getByLabel("Duration (minutes)")).toHaveValue("45");
  await expect(history).toContainText("60 min");
  expect(attempts).toEqual(["PATCH"]);
  fail = false;
  await page.getByRole("button", { name: "Save Session", exact: true }).click();
  await expect(history).toContainText("45 min");
  fail = true;
  await page.getByRole("button", { name: "Delete Boxing", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "The training service is temporarily unavailable" })).toBeVisible();
  await expect(history).toContainText("Boxing");
  await expect(page.getByRole("button", { name: "Delete Boxing", exact: true })).toBeEnabled();
  expect(attempts).toEqual(["PATCH", "PATCH", "DELETE", "DELETE", "DELETE"]);
  fail = false;
  await page.getByRole("button", { name: "Delete Boxing", exact: true }).click();
  await expect(history).not.toContainText("Boxing");
  await page.reload();
  await expect(history.getByRole("listitem")).toHaveCount(1);
});

const manual: TrainingHistorySession = {
  id: "backdated-boxing", source: "external", title: "Boxing", status: "done", training_day: "2026-10-09",
  activity: "boxing", duration_minutes: 60, effort: "hard", plan_id: null,
};

test("Today without manual history offers the simple form", async ({ page, baseURL }) => {
  await setup(page, baseURL!, false, false, []);
  await page.goto("/today");
  await expect(page.getByRole("button", { name: "Log Training", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Repeat last session" })).toHaveCount(0);
  await page.getByRole("button", { name: "Log Training", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Activity", exact: true })).toContainText("Select activity");
  await expect(page.getByLabel("Duration (minutes)")).toHaveValue("");
  await expect(page.getByRole("combobox", { name: "Effort", exact: true })).toContainText("Select effort");
});

test("repeat on Today needs only effort and save; a second session stays separate", async ({ page, baseURL }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => {
    // isolateFromNetwork deliberately aborts external Supabase/Sentry traffic.
    if (message.type() === "error" && message.text() !== "Failed to load resource: net::ERR_FAILED") errors.push(message.text());
  });
  page.on("requestfailed", request => {
    // Next cancels in-flight route prefetches when this test changes pages.
    if (new URL(request.url()).origin === new URL(baseURL!).origin && request.failure()?.errorText !== "net::ERR_ABORTED") {
      errors.push(`App resource failed: ${request.url()} (${request.failure()?.errorText})`);
    }
  });
  await page.setViewportSize({ width: 390, height: 844 });
  const submissions = await setup(page, baseURL!, false, false, [prescribed, manual]);
  let todayReads = 0;
  page.on("request", request => { if (new URL(request.url()).pathname === "/api/today") todayReads++; });
  await page.goto("/today");
  const repeat = page.getByRole("button", { name: "Repeat last session", exact: true });
  await expect(repeat).toContainText("Boxing · 60 min");
  await expect(repeat).not.toContainText("Last recorded");
  await expect(repeat).not.toContainText("Review and log");
  expect((await repeat.boundingBox())!.height).toBeLessThanOrEqual(80);
  const entryLink = page.getByRole("link", { name: "Log Training", exact: true });
  await expect(entryLink).toBeInViewport();
  await page.screenshot({ path: "/tmp/quick-log-today-first-viewport.png" });
  await entryLink.click();
  await expect(repeat).toBeInViewport();
  await page.screenshot({ path: "/tmp/quick-log-compact-row.png" });
  await repeat.focus();
  await page.keyboard.press("Enter");
  const effort = page.getByRole("combobox", { name: "Effort", exact: true });
  await expect(effort).toBeFocused();
  await expect(page.getByRole("dialog")).toContainText("Last effort: Hard");
  await expect(effort).toContainText("Select effort");
  await expect(effort).toHaveAccessibleDescription("Confirm today’s effort.");
  await expect(page.getByLabel("Duration (minutes)")).toHaveValue("60");
  expect(submissions).toHaveLength(0);
  await page.screenshot({ path: "/tmp/quick-log-review-mobile.png" });
  await page.getByRole("button", { name: "Save Session", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("Select an activity and effort");
  expect(submissions).toHaveLength(0);
  await effort.press("ArrowDown");
  await page.keyboard.press("Home");
  await page.keyboard.press("Enter");
  await expect(effort).toContainText("Easy");
  expect((await new AxeBuilder({ page }).include("dialog").analyze()).violations).toEqual([]);
  // Two synchronous submits must produce only one request, even before React renders busy state.
  await page.getByRole("form", { name: "Log Training", exact: true }).evaluate((form: HTMLFormElement) => {
    form.requestSubmit(); form.requestSubmit();
  });
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(submissions).toHaveLength(1);
  expect(submissions[0]).toMatchObject({ activity: "boxing", duration_minutes: 60, effort: "easy" });
  expect(submissions[0]).not.toHaveProperty("training_day");
  await expect.poll(() => todayReads).toBeGreaterThan(1);
  await expect(page.getByRole("status").filter({ hasText: "logged successfully" })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("today-recent-shortcut.png") });
  await page.getByRole("button", { name: "Log Training", exact: true }).click();
  await choose(page, page, "Activity", "Strength");
  await page.getByLabel("Duration (minutes)").fill("45");
  await choose(page, page, "Effort", "Moderate");
  await page.getByRole("button", { name: "Save Session", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(submissions).toHaveLength(2);
  expect(submissions[1].client_request_id).not.toBe(submissions[0].client_request_id);
  await page.goto("/history");
  const rows = page.locator(".history-list > li");
  await expect(rows).toHaveCount(4);
  await expect(rows.filter({ hasText: "Fri 09 Oct 2026" })).toContainText("Hard");
  await expect(rows.filter({ hasText: "Sun 18 Oct 2026" })).toHaveCount(2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test("History repeat retries the same occurrence, preserves the source and creates fresh repeats", async ({ page, baseURL }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const submissions = await setup(page, baseURL!, true, false, [prescribed, manual]);
  await page.goto("/history");
  await expect(page.getByRole("button", { name: "Repeat Strength & Power", exact: true })).toHaveCount(0);
  const source = page.locator(".history-list > li").filter({ hasText: "Fri 09 Oct 2026" });
  await source.getByRole("button", { name: "Repeat Boxing", exact: true }).click();
  await page.keyboard.press("Escape");
  expect(submissions).toHaveLength(0);
  await expect(source.getByRole("button", { name: "Repeat Boxing", exact: true })).toBeFocused();
  await source.getByRole("button", { name: "Repeat Boxing", exact: true }).click();
  await choose(page, page, "Effort", "Moderate");
  await page.getByRole("button", { name: "Save Session", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("response lost");
  await page.getByRole("button", { name: "Save Session", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(submissions).toHaveLength(2);
  expect(submissions[1]).toEqual(submissions[0]);
  await expect(page.locator(".history-list > li")).toHaveCount(3);
  await expect(page.getByRole("status").filter({ hasText: "logged successfully" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(source).toContainText("60 min");
  await expect(source).toContainText("Hard");
  await source.getByRole("button", { name: "Repeat Boxing", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Effort", exact: true })).toContainText("Select effort");
  await choose(page, page, "Effort", "Easy");
  await page.getByRole("button", { name: "Save Session", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(submissions[2].client_request_id).not.toBe(submissions[0].client_request_id);
  await page.reload();
  await expect(page.locator(".history-list > li")).toHaveCount(4);
  await expect(source).toContainText("Hard");
});

test("expired save reports sign-in requirement without changing history", async ({ page, baseURL }) => {
  await setup(page, baseURL!, false, false, [manual]);
  await page.route("**/api/training/sessions", route => route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Unauthorized" }) }));
  await page.goto("/history");
  await page.getByRole("button", { name: "Repeat Boxing", exact: true }).click();
  await choose(page, page, "Effort", "Easy");
  await page.getByRole("button", { name: "Save Session", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("Your session expired. Sign in again");
  await expect(page.getByRole("button", { name: "Save Session", exact: true })).toBeEnabled();
  await expect(page.locator(".history-list > li")).toHaveCount(1);
});


test("a dropped network response can retry without creating another session", async ({ page, baseURL }) => {
  const submissions = await setup(page, baseURL!, "network", false, [manual]);
  await page.goto("/history");
  await page.getByRole("button", { name: "Repeat Boxing", exact: true }).click();
  await choose(page, page, "Effort", "Easy");
  await page.getByRole("button", { name: "Save Session", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toBeVisible();
  await expect(page.getByLabel("Duration (minutes)")).toHaveValue("60");
  await page.getByRole("button", { name: "Save Session", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(submissions).toHaveLength(2);
  expect(submissions[1]).toEqual(submissions[0]);
  await expect(page.locator(".history-list > li")).toHaveCount(2);
});

test("Today logging remains available without an active plan", async ({ page, baseURL }) => {
  await setup(page, baseURL!, false, false, []);
  await page.route("**/api/today", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({
    active_plan: {}, today: { training_day: "2026-10-18" }, open_injuries: [], risk_watch: [],
  }) }));
  await page.goto("/today");
  await expect(page.getByRole("link", { name: "Build my plan" })).toBeVisible();
  await page.getByRole("button", { name: "Log Training", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
});


const mondayHistory: TrainingHistorySession[] = ["2026-10-12", "2026-10-05"].map(day => ({ ...manual, id: day, training_day: day }));

async function habitSetup(page: Page, baseURL: string, rows = mondayHistory, preferences?: TrainingHabitPreferences) {
  return setup(page, baseURL, false, false, rows, preferences, "2026-10-19");
}

test("one week yields a tentative suggestion with blank effort; no routine is created", async ({ page, baseURL }) => {
  const submissions = await habitSetup(page, baseURL!, mondayHistory.slice(0, 1));
  await page.goto("/today");
  const suggestion = page.getByRole("button", { name: "Suggested today", exact: true });
  await expect(suggestion).toContainText("Boxing · 60 min");
  await expect(suggestion).toHaveAccessibleDescription("Boxing · 60 min");
  await expect(page.getByText("Boxing every Monday?", { exact: true })).toHaveCount(0);
  await suggestion.click();
  await expect(page.getByRole("combobox", { name: "Effort", exact: true })).toContainText("Select effort");
  expect(submissions).toHaveLength(0);
});

test("confirm a pattern in one tap, persist it and log through the same form", async ({ page, baseURL }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const submissions = await habitSetup(page, baseURL!);
  await page.goto("/today");
  await expect(page.getByText("Boxing every Monday?", { exact: true })).toBeVisible();
  await expect(page.getByText("Logged two weeks in a row.", { exact: true })).toBeVisible();
  expect((await new AxeBuilder({ page }).include("#today-training-log").analyze()).violations).toEqual([]);
  await page.locator("#today-training-log").scrollIntoViewIfNeeded();
  await page.screenshot({ path: "/tmp/habit-pattern-mobile.png" });
  await page.getByRole("button", { name: "Yes, usually", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Routine saved." })).toBeVisible();
  expect(submissions).toHaveLength(0);
  await expect(page.getByRole("button", { name: "Your usual Monday", exact: true })).toContainText("60 min");
  await page.reload();
  await page.getByRole("button", { name: "Your usual Monday", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Effort", exact: true })).toContainText("Select effort");
  await choose(page, page, "Effort", "Easy");
  await page.getByRole("button", { name: "Save Session", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(submissions).toHaveLength(1);
  expect(submissions[0]).toMatchObject({ activity: "boxing", duration_minutes: 60, effort: "easy" });
  expect(submissions[0]).not.toHaveProperty("plan_id");
  await expect(page.getByRole("button", { name: "Your usual Monday", exact: true })).toHaveCount(0);
});

test("Not always is remembered; routines remain editable and suggestions can pause", async ({ page, baseURL }) => {
  await habitSetup(page, baseURL!);
  await page.goto("/today");
  await page.getByRole("button", { name: "Not always", exact: true }).click();
  await page.reload();
  await expect(page.getByText("Boxing every Monday?", { exact: true })).toHaveCount(0);
  await page.getByText("Training habits", { exact: true }).click();
  await page.getByRole("button", { name: "Suggest Monday Boxing again", exact: true }).click();
  await page.getByRole("button", { name: "Yes, usually", exact: true }).click();
  await page.getByText("Edit · 60 min", { exact: true }).click();
  const form = page.getByRole("form", { name: "Edit Monday Boxing routine", exact: true });
  await form.getByLabel("Minutes", { exact: true }).fill("45");
  await form.getByRole("button", { name: "Save routine", exact: true }).click();
  await expect(page.getByRole("button", { name: "Your usual Monday", exact: true })).toContainText("45 min");
  await page.getByLabel("Suggest from my history", { exact: true }).uncheck();
  await expect(page.getByRole("button", { name: "Your usual Monday", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Repeat last session", exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "Your usual Monday", exact: true })).toHaveCount(0);
});

test("preference errors do not pretend to confirm a routine", async ({ page, baseURL }) => {
  await habitSetup(page, baseURL!);
  await page.route("**/api/me", async route => {
    if (route.request().method() === "PUT") return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Couldn’t save. Try again." }) });
    await route.fallback();
  });
  await page.goto("/today");
  await page.getByRole("button", { name: "Yes, usually", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Couldn’t save" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Yes, usually", exact: true })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Your usual Monday", exact: true })).toHaveCount(0);
});

test("sparring history does not predict contact permission", async ({ page, baseURL }) => {
  await habitSetup(page, baseURL!, mondayHistory.map(row => ({ ...row, activity: "sparring", title: "Sparring" })));
  await page.goto("/today");
  await expect(page.getByRole("button", { name: "Repeat last session", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Suggested today", exact: true })).toHaveCount(0);
  await expect(page.getByText("Sparring every Monday?", { exact: true })).toHaveCount(0);
});

test("changed routines need confirmation; one-off changes do not overwrite them", async ({ page, baseURL }) => {
  const preferences: TrainingHabitPreferences = { enabled: true, decisions: [{ weekday: 0, activity: "boxing", duration_minutes: 60, state: "confirmed", decided_on: "2026-09-20" }] };
  const rows = mondayHistory.map(row => ({ ...row, activity: "strength" as const, title: "Strength", duration_minutes: 45 }));
  await habitSetup(page, baseURL!, rows, preferences);
  await page.goto("/today");
  await expect(page.getByRole("button", { name: "Your usual Monday", exact: true })).toContainText("Boxing");
  await expect(page.getByText("Switch Monday to strength?", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Yes, update", exact: true }).click();
  await expect(page.getByRole("button", { name: "Your usual Monday", exact: true })).toContainText("Strength · 45 min");
  await page.reload();
  await expect(page.getByRole("button", { name: "Your usual Monday", exact: true })).toContainText("Strength · 45 min");
});

for (const mode of ["coach", "injury"] as const) {
  test(`${mode} context outranks learned logging suggestions`, async ({ page, baseURL }) => {
    await habitSetup(page, baseURL!);
    await page.route("**/api/today", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({
      active_plan: { id: "plan-1", name: "Camp", phase: "SPP" },
      today: { training_day: "2026-10-19", recommendation_state: mode === "injury" ? "pull_back" : "train_as_planned",
        decision_tier: mode === "injury" ? "stop" : "green", next_session: { coach_led_contact: mode === "coach" ? "sparring" : undefined },
        session_scope: "today", completion_status: "not_started", session_label: "Today’s session" },
      open_injuries: [], risk_watch: [], week_summary: {}, quick_actions: [],
    }) }));
    await page.goto("/today");
    await expect(page.getByRole("button", { name: "Repeat last session", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Suggested today", exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Yes, usually", exact: true })).toHaveCount(0);
  });
}

test("retrying a lost routine response recovers the saved intention", async ({ page, baseURL }) => {
  const submissions = await habitSetup(page, baseURL!);
  const initialRead = page.waitForResponse(response => new URL(response.url()).pathname === "/api/me" && response.request().method() === "GET");
  await page.goto("/today");
  const initial = await (await initialRead).json();
  let saved: TrainingHabitPreferences | undefined;
  await page.route("**/api/me", async route => {
    if (route.request().method() === "PUT") {
      if (!saved) {
        saved = route.request().postDataJSON().training_habits;
        return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Response lost. Retry." }) });
      }
      return route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ detail: "Routines changed on another device. Refresh and try again." }) });
    }
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({ ...initial, profile: {
      ...initial.profile, training_habits: saved ?? initial.profile.training_habits, training_habits_revision: saved ? 1 : 0,
    } }) });
  });
  await page.getByRole("button", { name: "Yes, usually", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Response lost" })).toBeVisible();
  await page.getByRole("button", { name: "Yes, usually", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Routine saved." })).toBeVisible();
  await expect(page.getByRole("button", { name: "Your usual Monday", exact: true })).toBeVisible();
  expect(submissions).toHaveLength(0);
});

for (const requiresUpdate of [false, true]) {
test(`sparring suggestion requires current contact clearance (update pending: ${requiresUpdate})`, async ({ page, baseURL }) => {
  const submissions = await habitSetup(page, baseURL!, mondayHistory.map(row => ({ ...row, activity: "sparring", title: "Sparring" })));
  await page.route("**/api/today", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({
    active_plan: { id: "plan-1", name: "Camp", phase: "SPP" },
    today: { training_day: "2026-10-19", recommendation_state: "train_as_planned", decision_tier: "green",
      next_session: {}, session_scope: "none", completion_status: "not_started", session_label: "No session" },
    effective_clinician_clearance: { level: "train_contact", scopes: [], requires_update: requiresUpdate, limited_by: [] },
    open_injuries: [], risk_watch: [], week_summary: {}, quick_actions: [],
  }) }));
  await page.goto("/today");
  const suggestion = page.getByRole("button", { name: "Suggested today", exact: true });
  if (requiresUpdate) {
    await expect(page.getByRole("button", { name: "Repeat last session", exact: true })).toBeVisible();
    await expect(suggestion).toHaveCount(0);
    return;
  }
  await expect(suggestion).toContainText("Sparring · 60 min");
  await suggestion.click();
  await expect(page.getByRole("combobox", { name: "Effort", exact: true })).toContainText("Select effort");
  expect(submissions).toHaveLength(0);
});

}

test("two confirmed weekday routines remain separate logging shortcuts", async ({ page, baseURL }) => {
  const preferences: TrainingHabitPreferences = { enabled: true, decisions: [
    { weekday: 0, activity: "boxing", duration_minutes: 60, state: "confirmed", decided_on: "2026-09-20" },
    { weekday: 0, activity: "strength", duration_minutes: 45, state: "confirmed", decided_on: "2026-09-20" },
  ] };
  const submissions = await habitSetup(page, baseURL!, mondayHistory, preferences);
  await page.goto("/today");
  const usual = page.getByRole("button", { name: "Your usual Monday", exact: true });
  await expect(usual).toContainText("Boxing · 60 min");
  await usual.click();
  await choose(page, page, "Effort", "Easy");
  await page.getByRole("button", { name: "Save Session", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(usual).toContainText("Strength · 45 min");
  await usual.click();
  await expect(page.getByLabel("Duration (minutes)")).toHaveValue("45");
  await expect(page.getByRole("combobox", { name: "Effort", exact: true })).toContainText("Select effort");
  expect(submissions).toHaveLength(1);
});

test("confirmed routines survive a failed history read without detecting new patterns", async ({ page, baseURL }) => {
  const preferences: TrainingHabitPreferences = { enabled: true, decisions: [
    { weekday: 0, activity: "boxing", duration_minutes: 50, state: "confirmed", decided_on: "2026-09-20" },
  ] };
  const submissions = await habitSetup(page, baseURL!, mondayHistory, preferences);
  await page.route("**/api/training/history**", route => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "History unavailable." }) }));
  await page.goto("/today");
  const usual = page.getByRole("button", { name: "Your usual Monday", exact: true });
  await expect(usual).toContainText("Boxing · 50 min");
  await page.getByText("Training habits", { exact: true }).click();
  await expect(page.getByText("History unavailable.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Yes, usually", exact: true })).toHaveCount(0);
  await usual.click();
  await expect(page.getByLabel("Duration (minutes)")).toHaveValue("50");
  await expect(page.getByRole("combobox", { name: "Effort", exact: true })).toContainText("Select effort");
  await expect(page.getByRole("dialog")).not.toContainText("Last effort:");
  expect(submissions).toHaveLength(0);
  await choose(page, page, "Effort", "Easy");
  await page.getByRole("button", { name: "Save Session", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(usual).toHaveCount(0); // The locally saved session remains known during the outage.
  expect(submissions).toHaveLength(1);
});

test("failed history leaves simple logging available without inferred suggestions", async ({ page, baseURL }) => {
  await habitSetup(page, baseURL!);
  await page.route("**/api/training/history**", route => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "History unavailable." }) }));
  await page.goto("/today");
  await page.getByText("Training habits", { exact: true }).click();
  await expect(page.getByText("History unavailable.", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Suggested today", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Yes, usually", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Log Training", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
});

test("history failure never restores a confirmed shortcut blocked by readiness", async ({ page, baseURL }) => {
  const preferences: TrainingHabitPreferences = { enabled: true, decisions: [
    { weekday: 0, activity: "boxing", duration_minutes: 50, state: "confirmed", decided_on: "2026-09-20" },
  ] };
  await habitSetup(page, baseURL!, mondayHistory, preferences);
  await page.route("**/api/training/history**", route => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "History unavailable." }) }));
  await page.route("**/api/today", route => route.fulfill({ contentType: "application/json", body: JSON.stringify({
    active_plan: { id: "plan-1", name: "Camp", phase: "SPP" },
    today: { training_day: "2026-10-19", recommendation_state: "pull_back", decision_tier: "stop",
      next_session: {}, session_scope: "none", completion_status: "not_started", session_label: "No session" },
    open_injuries: [], risk_watch: [], week_summary: {}, quick_actions: [],
  }) }));
  await page.goto("/today");
  await expect(page.getByRole("button", { name: "Log Training", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Your usual Monday", exact: true })).toHaveCount(0);
});
