import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { isolateFromNetwork } from "./support";

const asOf = "2026-10-19T12:00:00Z";
const exercise = (key: string, name: string, values = {}, best_loads: object[] = []) => ({ id: `key:${key}`, name,
  identity_kind: "canonical", latest_day: "2026-10-19", latest_values: values, latest_confirmed_as_prescribed: false, best_loads });
const exercises = [
  exercise("back-squat", "Back Squat", { sets: 3, reps: 5 }, [{ value: 100, unit: "kg", training_day: "2026-01-01", basis: "reported" }, { value: 200, unit: "lb", training_day: "2026-02-01", basis: "reported" }]),
  exercise("back-squat-paused", "Back Squat (Paused)", { sets: 3, reps: 5 }),
  exercise("push-ups", "Push-ups", { sets: 3, reps: 15 }),
  exercise("plank", "Plank", { duration: { value: 120, unit: "seconds" } }),
  exercise("sprint-intervals", "Sprint Intervals", { rounds: 6 }),
  { ...exercise("old-carry", "Older loaded carry", { distance: { value: 50, unit: "meters" } }), latest_day: "2025-01-01" },
  { ...exercise("legacy", "Legacy Squat", { reps: 10 }), id: "log:legacy", identity_kind: "legacy" },
];
const performance = (id: string, day: string, status = "modified") => ({ id, training_day: day, block: {
  name: "Back Squat", kind: "exercise", status, prescribed: { sets: 4, reps: 5, load: { display: "90 kg" }, rest: { value: 120, unit: "seconds" } },
  actual: status === "modified" ? { sets: 3, reps: 5, load: { value: 80, unit: "kg" }, rest: { value: 180, unit: "seconds" }, effort: { value: 8 } } : {},
  notes: "Kept the bar controlled", reason: status === "modified" ? "fatigue" : null, responses: [],
} });

async function setup(page: Page, baseURL: string) {
  await isolateFromNetwork(page, baseURL);
  const now = new Date(asOf); await page.clock.setFixedTime(now);
  const key = `sb-${new URL(process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://stub.supabase.co").hostname.split(".")[0]}-auth-token`;
  await page.addInitScript(([key, value]) => localStorage.setItem(key, value), [key, JSON.stringify({
    access_token: "exercise-test", refresh_token: "test", token_type: "bearer", expires_at: now.getTime() / 1000 + 86400,
    user: { id: "00000000-0000-4000-8000-000000000001", email: "fighter@example.com", aud: "authenticated", role: "authenticated", app_metadata: {}, user_metadata: {} },
  })]);
  const requests: string[] = []; let failed = false;
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url()); const path = url.pathname;
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/me") return json({ profile: { athlete_id: "00000000-0000-4000-8000-000000000001", email: "fighter@example.com", full_name: "Carlos", role: "athlete", access_status: "approved", technical_style: ["boxing"], tactical_style: [], athlete_timezone: "Europe/London", athlete_locale: "en", appearance_mode: "dark", nutrition_profile: {}, date_of_birth: "1995-01-01", meets_minimum_age: true, is_minor: false, terms_accepted: true, health_consent_granted: true, private_trial_ack_at: asOf }, plan_count: 0, latest_plan: null, latest_intake: null, username_rate_limit: {} });
    if (path === "/api/training/history") return json({ sessions: [{ id: "session", title: "Strength session", source: "unlxck", status: "done", training_day: "2026-10-19" }] });
    if (path === "/api/training/history/unlxck/session") return json({ session: { id: "session", title: "Strength session", source: "unlxck", status: "done", training_day: "2026-10-19" }, blocks: [], prescription_source: "unavailable", message: "Detailed exercise records weren't captured for this session." });
    if (path === "/api/history/exercise-library") { requests.push(path); return json({ exercises, as_of: asOf, coverage: "retained_logs" }); }
    if (path === "/api/history/exercise-performances") {
      expect(route.request().method()).toBe("GET"); expect(route.request().headers().authorization).toBe("Bearer exercise-test");
      requests.push(url.search);
      if (url.searchParams.get("exercise") !== "key:back-squat") return json({ performances: [{ ...performance("other", "2025-01-01", "as_prescribed"), block: { ...performance("other", "2025-01-01").block, name: "Older loaded carry" } }], next_cursor: null });
      if (url.searchParams.has("cursor")) {
        if (!failed) { failed = true; return json({ detail: "unavailable" }, 503); }
        return json({ performances: [performance("first", "2026-10-19"), performance("old-best", "2026-01-01", "as_prescribed")], next_cursor: null });
      }
      return json({ performances: [performance("first", "2026-10-19"), performance("skip", "2026-10-12", "skipped")], next_cursor: "next" });
    }
    if (path === "/api/plans/active") return json({ detail: "No active plan" }, 404);
    if (path === "/api/plans") return json([]);
    return json({ notifications: [], unread_count: 0, level: 1, total_xp: 0 });
  });
  return requests;
}

for (const width of [390, 1280]) {
  test(`personal exercise records, search, paging and session isolation at ${width}px`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height: 844 });
    const requests = await setup(page, baseURL!); const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto("/history"); await page.getByRole("tab", { name: "Exercises", exact: true }).click();
    const trigger = page.getByRole("button", { name: "View Back Squat performance history", exact: true });
    await expect(trigger).toBeVisible(); await expect(trigger).toContainText("100 kg · 200 lb");
    await expect(page.getByRole("list", { name: "Your exercises", exact: true }).getByRole("listitem")).toHaveCount(6);
    await expect(page.getByRole("button", { name: "View Push-ups performance history", exact: true })).toContainText("3 × 15");
    await expect(page.getByRole("button", { name: "View Plank performance history", exact: true })).toContainText("2 min");
    expect(requests).toEqual(["/api/history/exercise-library"]);
    const search = page.getByRole("searchbox", { name: "Find an exercise" });
    await search.fill("older"); await expect(page.getByRole("button", { name: "View Older loaded carry performance history" })).toBeVisible();
    await expect(trigger).toHaveCount(0); await search.fill("");
    await page.getByRole("heading", { name: "History", exact: true }).click();
    if (process.env.EXERCISE_QA_DIR) await page.screenshot({ path: `${process.env.EXERCISE_QA_DIR}/exercise-library-${width}.png` });
    await trigger.focus(); await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog", { name: "Back Squat", exact: true });
    await expect(dialog).toContainText("Performance history"); await expect(dialog).toContainText("80 kg");
    await expect(dialog).toContainText("180 seconds"); await expect(dialog).toContainText("Other performed values are unknown");
    await expect(dialog.getByRole("button", { name: "Close exercise history" })).toBeFocused();
    await page.keyboard.press("Tab"); expect(await dialog.evaluate(node => node.contains(document.activeElement))).toBe(true);
    expect((await new AxeBuilder({ page }).include("dialog").analyze()).violations).toEqual([]);
    const box = await dialog.boundingBox(); expect(box!.width).toBeLessThanOrEqual(width); expect(box!.x).toBeGreaterThanOrEqual(0);
    await dialog.getByRole("button", { name: "Load earlier performances" }).click();
    await expect(dialog.getByRole("alert")).toBeVisible(); await expect(dialog.locator("ol > li")).toHaveCount(2);
    await dialog.getByRole("button", { name: "Retry" }).click(); await expect(dialog.locator("ol > li")).toHaveCount(3);
    await page.keyboard.press("Escape"); await expect(dialog).toHaveCount(0); await expect(trigger).toBeFocused();
    const calls = requests.length; await trigger.click(); await expect(dialog.locator("ol > li")).toHaveCount(3); expect(requests).toHaveLength(calls);
    if (process.env.EXERCISE_QA_DIR) await page.screenshot({ path: `${process.env.EXERCISE_QA_DIR}/exercise-history-${width}.png` });
    await page.keyboard.press("Escape");
    await page.getByRole("tab", { name: "Sessions", exact: true }).click(); await page.getByRole("button", { name: /View Strength session details/ }).click();
    await expect(page.getByRole("dialog", { name: "Strength session" })).toBeVisible(); await page.keyboard.press("Escape");
    await page.getByRole("tab", { name: "Exercises", exact: true }).click(); await trigger.click();
    await expect(dialog.locator("ol > li")).toHaveCount(3); expect(requests).toHaveLength(calls);
    expect(errors).toEqual([]);
  });
}
