import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { isolateFromNetwork } from "./support";
import type { TrainingHistorySession } from "../lib/training-history";

const athlete = "00000000-0000-4000-8000-000000000001";
const token = "log-training-test-token";
const storageKey = `sb-${new URL(process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://stub.supabase.co").hostname.split(".")[0]}-auth-token`;
const prescribed: TrainingHistorySession = {
  id: "prescribed", source: "unlxck", title: "Strength & Power", status: "done", training_day: "2026-10-10",
  activity: null, duration_minutes: null, effort: null, plan_id: "prior-plan",
  session_rpe: 7, notes: "Coach session",
};

async function setup(page: Page, baseURL: string, lostResponse = false) {
  await isolateFromNetwork(page, baseURL);
  await page.addInitScript(([key, value]) => localStorage.setItem(key, value), [storageKey, JSON.stringify({
    access_token: token, refresh_token: "test-refresh", token_type: "bearer",
    expires_in: 86400, expires_at: Math.floor(Date.now() / 1000) + 86400,
    user: { id: athlete, email: "fighter@example.com", aud: "authenticated", role: "authenticated", app_metadata: {}, user_metadata: {} },
  })]);
  let sessions = [prescribed];
  const submissions: Record<string, unknown>[] = [];
  await page.route("**/api/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/me") return json({ profile: {
      athlete_id: athlete, email: "fighter@example.com", full_name: "Carlos", role: "athlete", access_status: "approved",
      technical_style: ["boxing"], tactical_style: [], stance: "orthodox", professional_status: "professional", record: "",
      athlete_timezone: "Europe/London", athlete_locale: "en", appearance_mode: "dark", nutrition_profile: {},
      date_of_birth: "1995-01-01", meets_minimum_age: true, is_minor: false, terms_accepted: true,
      health_consent_granted: true, private_trial_ack_at: "2026-01-01T12:00:00Z",
    }, plan_count: 0, latest_plan: null, latest_intake: null, username_rate_limit: {} });
    if (path === "/api/plans/active") return json({ detail: "No active plan" }, 404);
    if (path === "/api/plans") return json([]);
    if (path === "/api/training/history") return json({ sessions });
    if (path === "/api/training/sessions" && request.method() === "POST") {
      expect(request.headers().authorization).toBe(`Bearer ${token}`);
      const body = request.postDataJSON();
      submissions.push(body);
      if (!sessions.some(row => row.source === "external")) sessions = [{
        id: "00000000-0000-4000-8000-000000000010", source: "external", training_day: body.training_day ?? "2026-10-10", status: "done",
        plan_id: null,
        title: "Sparring", activity: body.activity, duration_minutes: body.duration_minutes, effort: body.effort,
      }, ...sessions];
      if (lostResponse && submissions.length === 1) return json({ detail: "Saved, but response lost. Retry." }, 503);
      return json(sessions[0], 201);
    }
    if (path.startsWith("/api/training/sessions/") && request.method() === "PATCH") {
      const body = request.postDataJSON();
      sessions[0] = { ...sessions[0], ...body, title: "Boxing" };
      return json(sessions[0]);
    }
    if (path.startsWith("/api/training/sessions/") && request.method() === "DELETE") {
      sessions = sessions.filter(row => row.source !== "external");
      return route.fulfill({ status: 204 });
    }
    return json({ notifications: [], unread_count: 0, level: 1, total_xp: 0 });
  });
  return submissions;
}

for (const width of [390, 1280]) {
  test(`Plan logs, edits and deletes external work without a plan (${width}px)`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height: 844 });
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    const submissions = await setup(page, baseURL!);
    await page.goto("/plan");
    await page.getByRole("button", { name: "Log Training", exact: true }).click();
    const form = page.getByRole("form", { name: "Log Training", exact: true });
    await expect(form.locator("input[required], select[required]")).toHaveCount(3);
    await expect(form.getByLabel("Training date (optional)")).toBeHidden();
    await form.getByRole("combobox", { name: "Activity", exact: true }).selectOption("sparring");
    await form.getByLabel("Duration (minutes)").fill("60");
    await form.getByRole("combobox", { name: "Effort", exact: true }).selectOption("hard");
    // Compare rendered styling with the existing Plan CTA, catching unstyled
    // default buttons even if saving still works functionally.
    const ctaAppearance = (element: Element) => {
      const css = getComputedStyle(element);
      return [css.backgroundColor, css.backgroundImage, css.borderRadius, css.color];
    };
    expect(await form.getByRole("button", { name: "Save Session", exact: true }).evaluate(ctaAppearance))
      .toEqual(await page.getByRole("link", { name: "Quick Build New Plan" }).evaluate(ctaAppearance));
    await page.screenshot({ path: test.info().outputPath("log-training-form.png") });
    expect((await new AxeBuilder({ page }).include('[aria-label="Your Training"]').analyze()).violations).toEqual([]);
    await form.getByRole("button", { name: "Save Session", exact: true }).click();
    const history = page.getByRole("list", { name: "Training history" });
    await expect(history).toContainText("Added by you · Completed · 60 min · Hard");
    await expect(history).toContainText("Strength & Power");
    await page.screenshot({ path: test.info().outputPath("unified-training-history.png") });
    await expect(history.getByRole("button", { name: "Edit Strength & Power" })).toHaveCount(0);
    expect(submissions[0]).toMatchObject({ activity: "sparring", duration_minutes: 60, effort: "hard" });
    expect(Object.keys(submissions[0]).sort()).toEqual(["activity", "client_request_id", "duration_minutes", "effort"]);
    await page.reload();
    await page.getByRole("button", { name: "Edit Sparring", exact: true }).click();
    await page.getByRole("combobox", { name: "Activity", exact: true }).selectOption("boxing");
    await page.getByLabel("Duration (minutes)").fill("45");
    await page.getByRole("combobox", { name: "Effort", exact: true }).selectOption("moderate");
    await page.getByRole("button", { name: "Save Session", exact: true }).click();
    await expect(history).toContainText("45 min · Moderate");
    await page.goto("/history");
    await expect(page.locator(".history-list")).toContainText("Boxing");
    await expect(page.locator(".history-list")).toContainText("Added by you");
    await expect(page.locator(".history-list")).toContainText("45 min");
    await expect(page.locator(".history-list")).toContainText("RPE 7/10");
    await expect(page.locator(".history-list")).toContainText("Coach session");
    await expect(page.locator(".history-list > li")).toHaveCount(2);
    await page.goto("/plan");
    await page.getByRole("button", { name: "Delete Boxing", exact: true }).click();
    await expect(history.getByRole("listitem")).toHaveCount(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
  });
}

test("retry after a lost save response keeps the same request ID", async ({ page, baseURL }) => {
  const submissions = await setup(page, baseURL!, true);
  await page.goto("/plans");
  await page.getByRole("button", { name: "Log Training", exact: true }).click();
  await page.getByRole("combobox", { name: "Activity", exact: true }).selectOption("sparring");
  await page.getByLabel("Duration (minutes)").fill("60");
  await page.getByRole("combobox", { name: "Effort", exact: true }).selectOption("hard");
  await page.getByRole("button", { name: "Save Session", exact: true }).click();
  await expect(page.getByRole("region", { name: "Your Training" }).getByRole("alert")).toContainText("response lost");
  await page.getByRole("button", { name: "Save Session", exact: true }).click();
  await expect(page.getByRole("list", { name: "Training history" }).getByRole("listitem")).toHaveCount(2);
  expect(submissions).toHaveLength(2);
  expect(submissions[1].client_request_id).toBe(submissions[0].client_request_id);
});

test("log yesterday's sparring with the optional date and preserve it after editing", async ({ page, baseURL }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const submissions = await setup(page, baseURL!);
  await page.goto("/plans");
  await page.getByRole("button", { name: "Log Training", exact: true }).click();
  await page.getByRole("combobox", { name: "Activity", exact: true }).selectOption("sparring");
  await page.getByLabel("Duration (minutes)").fill("60");
  await page.getByRole("combobox", { name: "Effort", exact: true }).selectOption("hard");
  await page.getByText("Training date · Current day", { exact: true }).click();
  await page.getByLabel("Training date (optional)").fill("2026-10-09");
  await page.screenshot({ path: test.info().outputPath("backdated-training-form.png") });
  expect((await new AxeBuilder({ page }).include('[aria-label="Your Training"]').analyze()).violations).toEqual([]);
  await page.getByRole("button", { name: "Save Session", exact: true }).click();
  expect(submissions[0]).toMatchObject({ activity: "sparring", duration_minutes: 60, effort: "hard", training_day: "2026-10-09" });
  const history = page.getByRole("list", { name: "Training history" });
  await expect(history).toContainText("Fri 09 Oct 2026");
  await page.reload();
  await page.getByRole("button", { name: "Edit Sparring", exact: true }).click();
  await page.getByLabel("Duration (minutes)").fill("45");
  await page.getByRole("button", { name: "Save Session", exact: true }).click();
  await expect(history).toContainText("Fri 09 Oct 2026");
  await expect(history).toContainText("45 min · Hard");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
