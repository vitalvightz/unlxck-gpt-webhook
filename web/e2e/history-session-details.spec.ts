import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { isolateFromNetwork } from "./support";

const day = "2026-10-19";
const rows = [
  { id: "strength", source: "unlxck", completion_origin: "reported", title: "Strength & Power", status: "modified", training_day: day, plan_id: "old", session_rpe: 7 },
  { id: "rehab", source: "unlxck", title: "Today's rehab", status: "done", training_day: day },
  { id: "manual", source: "external", title: "Boxing", activity: "boxing", duration_minutes: 40, effort: "hard", status: "done", training_day: day },
  { id: "legacy", source: "unlxck", title: "Legacy strength", status: "done", training_day: day },
];
const blocks = [
  { name: "Back squat", kind: "exercise", prescribed: { sets: 4, reps: 6, load: { display: "80 kg" }, rest: { value: 120, unit: "seconds" } }, actual: { sets: 3, reps: 5, load: { value: 75, unit: "kg" }, rest: { value: 150, unit: "seconds" } }, status: "modified", responses: [] },
  { name: "Plank", kind: "exercise", prescribed: { sets: 3, duration: { value: 45, unit: "seconds" } }, actual: {}, status: "as_prescribed", responses: [] },
  { name: "Bike intervals", kind: "exercise", prescribed: { rounds: 5, work: { value: 30, unit: "seconds" }, rest: { value: 90, unit: "seconds" } }, actual: {}, status: "skipped", responses: [] },
];

async function setup(page: Page, baseURL: string) {
  await isolateFromNetwork(page, baseURL);
  const now = new Date(`${day}T12:00:00Z`);
  await page.clock.setFixedTime(now);
  const key = `sb-${new URL(process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://stub.supabase.co").hostname.split(".")[0]}-auth-token`;
  await page.addInitScript(([key, value]) => localStorage.setItem(key, value), [key, JSON.stringify({
    access_token: "history-test", refresh_token: "test", token_type: "bearer", expires_at: now.getTime() / 1000 + 86400,
    user: { id: "00000000-0000-4000-8000-000000000001", email: "fighter@example.com", aud: "authenticated", role: "authenticated", app_metadata: {}, user_metadata: {} },
  })]);
  const requests: string[] = [];
  let fail = false;
  await page.route("**/api/**", async route => {
    const path = new URL(route.request().url()).pathname;
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/me") return json({ profile: { athlete_id: "00000000-0000-4000-8000-000000000001", email: "fighter@example.com", full_name: "Carlos", role: "athlete", access_status: "approved", technical_style: ["boxing"], tactical_style: [], athlete_timezone: "Europe/London", athlete_locale: "en", appearance_mode: "dark", nutrition_profile: {}, date_of_birth: "1995-01-01", meets_minimum_age: true, is_minor: false, terms_accepted: true, health_consent_granted: true, private_trial_ack_at: `${day}T12:00:00Z` }, plan_count: 0, latest_plan: null, latest_intake: null, username_rate_limit: {} });
    if (path === "/api/training/history") return json({ sessions: rows });
    if (path.startsWith("/api/training/history/")) {
      expect(route.request().method()).toBe("GET");
      requests.push(path);
      if (fail) { fail = false; return json({ detail: "unavailable" }, 503); }
      const id = path.split("/").at(-1);
      return json({ session: rows.find(row => row.id === id), prescription_source: id === "manual" ? "manual" : "snapshot",
        blocks: id === "strength" ? blocks : id === "rehab" ? [
          { name: "Calf raise", kind: "rehab", prescribed: { sets: 3, reps: 10 }, actual: {}, status: "done_as_shown", completed_dose: { sets: 3, reps: 10, completion_state: "quantified" }, responses: [] },
          { name: "Ankle hold", kind: "rehab", prescribed: { duration: { value: 30, unit: "seconds" } }, actual: {}, status: "stopped", completed_dose: { completion_state: "partial_amount_unknown" }, responses: [] },
        ] : [], message: id === "legacy" ? "Detailed exercise records weren't captured for this session." : null });
    }
    if (path === "/api/plans/active") return json({ detail: "No active plan" }, 404);
    if (path === "/api/plans") return json([]);
    return json({ notifications: [], unread_count: 0, level: 1, total_xp: 0, logs: [] });
  });
  return { requests, failNext: () => { fail = true; } };
}

for (const width of [390, 1280]) {
  test(`History session sheet: evidence, focus, cache and actions at ${width}px`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height: 844 });
    const { requests, failNext } = await setup(page, baseURL!);
    const errors: string[] = []; page.on("pageerror", error => errors.push(error.message));
    await page.goto("/history");
    const trigger = page.getByRole("button", { name: /View Strength & Power details/ });
    await expect(trigger).toBeVisible();
    expect(requests).toHaveLength(0);
    if (process.env.HISTORY_QA_DIR) await page.screenshot({ path: `${process.env.HISTORY_QA_DIR}/history-${width}.png` });
    await trigger.focus(); await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog", { name: "Strength & Power" });
    await expect(dialog.getByRole("heading", { name: "Back squat" })).toBeVisible();
    await expect(dialog.getByRole("region", { name: "Performance: Back squat" })).toContainText("75 kg");
    await expect(dialog).toContainText("Confirmed completed as prescribed");
    await expect(dialog).toContainText("Skipped. No performance values logged.");
    await expect(dialog.getByRole("button", { name: "Close session details" })).toBeFocused();
    await page.keyboard.press("Tab");
    expect(await dialog.evaluate(element => element.contains(document.activeElement))).toBe(true);
    const box = await dialog.boundingBox(); expect(box!.width).toBeLessThanOrEqual(width); expect(box!.x).toBeGreaterThanOrEqual(0);
    if (width >= 900) {
      expect(box!.width).toBeGreaterThan(width * .9);
      const overview = await dialog.getByRole('region', { name: 'Session overview' }).boundingBox();
      const records = await dialog.getByRole('heading', { name: 'Exercises & training blocks' }).boundingBox();
      expect(overview!.x + overview!.width).toBeLessThan(records!.x);
    }
    expect((await new AxeBuilder({ page }).include("dialog").analyze()).violations).toEqual([]);
    await page.keyboard.press("Escape"); await expect(dialog).toHaveCount(0); await expect(trigger).toBeFocused();
    await trigger.click(); await expect(dialog.getByText("Back squat", { exact: true })).toBeVisible();
    if (process.env.HISTORY_QA_DIR) await page.screenshot({ path: `${process.env.HISTORY_QA_DIR}/session-details-${width}.png` });
    expect(requests).toHaveLength(1);
    await dialog.getByRole("button", { name: "Close session details" }).click();
    await page.getByRole("button", { name: /View Today's rehab details/ }).click();
    const rehab = page.getByRole("dialog", { name: "Today's rehab" });
    await expect(rehab).toContainText("Completed amount unknown.");
    await expect(rehab.getByRole("region", { name: "Performance: Calf raise" })).toContainText("10");
    await page.keyboard.press("Escape");
    failNext(); await page.getByRole("button", { name: /View Legacy strength details/ }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Retry" }).click();
    await expect(page.getByRole("dialog")).toContainText("Detailed exercise records weren't captured");
    await page.keyboard.press("Escape");
    const manual = page.getByRole("button", { name: /View Boxing details/ });
    await manual.click(); await expect(page.getByRole("dialog")).toContainText("40 min recorded");
    await expect(page.getByRole("dialog")).toContainText("No exercises recorded. Only the session’s activity, duration and effort were logged.");
    await expect(page.getByRole("dialog").locator("ol")).toHaveCount(0);
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Edit Boxing", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Edit session" })).toBeVisible();
    await expect(page.getByRole("dialog")).not.toContainText("Session details");
    await page.keyboard.press("Escape");
    expect(errors).toEqual([]);
  });
}
