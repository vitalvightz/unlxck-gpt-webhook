import { expect, test, type Page } from "@playwright/test";
import { isolateFromNetwork } from "./support";

// Nutrition is the weight tracker: the old workspace form, its BMI/weight-source
// plumbing and the "Coming soon" gate are gone. Set WEIGHT_TRACKER_SCREENSHOTS
// to a directory to capture the page at phone and desktop widths.
const shots = process.env.WEIGHT_TRACKER_SCREENSHOTS;

function workspace(isMinor: boolean) {
  return {
    athlete_id: "athlete-1",
    source: "intake",
    intake_id: null,
    nutrition_profile: { sex: "male", age: isMinor ? 16 : 27, height_cm: 178 },
    shared_camp_context: {
      fight_date: "2026-11-14",
      target_weight_kg: isMinor ? null : 70,
      current_weight_kg: 73.4,
      current_weight_source: "latest_bodyweight_log",
      session_types_by_day: {},
      hard_sparring_days: [],
      support_work_days: [],
      training_availability: [],
    },
    s_and_c_preferences: {},
    nutrition_readiness: {},
    nutrition_monitoring: {
      daily_bodyweight_log: [
        { date: "2026-10-21", weight_kg: 74.1, time: "07:10", is_fasted: true, notes: null },
        { date: "2026-10-23", weight_kg: 73.6, time: "07:05", is_fasted: true, notes: null },
        { date: "2026-10-26", weight_kg: 73.4, time: "07:00", is_fasted: true, notes: "Morning, after toilet" },
      ],
    },
    nutrition_coach_controls: {},
    derived: { days_until_fight: 19, weight_cut_pct: 4.6, readiness_flags: [], missing_required_fields: [], foundation_status: "ready" },
  };
}

async function signInAthlete(page: Page, baseURL: string, { isMinor }: { isMinor: boolean }) {
  await isolateFromNetwork(page, baseURL);
  const key = `sb-${new URL(process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://stub.supabase.co").hostname.split(".")[0]}-auth-token`;
  await page.addInitScript(([key, value]) => localStorage.setItem(key, value), [key, JSON.stringify({
    access_token: "fixture-token", refresh_token: "fixture", token_type: "bearer", expires_at: Math.floor(Date.now() / 1000) + 86400,
    user: { id: "athlete-1", email: "fighter@example.com", aud: "authenticated", role: "authenticated", app_metadata: {}, user_metadata: {} },
  })]);
  const saves: unknown[] = [];
  let current = workspace(isMinor);
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/nutrition/current") {
      if (request.method() === "PUT") {
        const body = request.postDataJSON();
        saves.push(body);
        current = { ...current, nutrition_monitoring: body.nutrition_monitoring };
      }
      return route.fulfill({ json: current });
    }
    if (path === "/api/me") {
      return route.fulfill({ json: {
        profile: { athlete_id: "athlete-1", full_name: "Alex", role: "athlete", access_status: "approved", starting_path: "plan_first",
          technical_style: ["boxing"], tactical_style: [], athlete_timezone: "UTC", athlete_locale: "en", appearance_mode: "dark",
          nutrition_profile: {}, date_of_birth: isMinor ? "2010-01-01" : "1999-01-01", meets_minimum_age: true, is_minor: isMinor,
          terms_accepted: true, health_consent_granted: true, private_trial_ack_at: "2026-01-01T00:00:00Z" },
        plan_count: 0, latest_plan: null, latest_intake: null, username_rate_limit: {},
      } });
    }
    return route.fulfill({ json: path === "/api/plans" ? [] : { notifications: [], unread_count: 0 } });
  });
  return saves;
}

for (const [width, height] of [[390, 844], [1280, 800]] as const) {
  test(`Nutrition is a weight tracker without the old workspace (${width}px)`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const saves = await signInAthlete(page, baseURL!, { isMinor: false });

    await page.goto("/nutrition/bodyweight-log");
    await expect(page).toHaveURL(/\/nutrition$/);
    await expect(page.getByRole("heading", { level: 1, name: "Weight tracker" })).toBeVisible();
    await expect(page.getByText("70.0 kg", { exact: true })).toBeVisible();
    await expect(page.getByText("19 days", { exact: true })).toBeVisible();
    for (const removed of ["BMI", "Weight source", "Nutrition workspace", "Save nutrition workspace", "COMING SOON"]) {
      await expect(page.getByText(removed, { exact: true })).toHaveCount(0);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if (shots) await page.screenshot({ path: `${shots}/weight-tracker-${width}.png`, fullPage: true });

    await page.getByLabel("Weight (kg)").fill("73.1");
    await page.getByRole("button", { name: "Save entry" }).click();
    await expect(page.getByText("Bodyweight entry saved.")).toBeVisible();
    expect(saves).toHaveLength(1);

    if (width === 1280) {
      const navLink = page.getByRole("link", { name: /Weight tracker/ }).first();
      await expect(navLink).toHaveAttribute("href", "/nutrition");
      await expect(navLink).toHaveCSS("pointer-events", "auto");
    }
    expect(errors).toEqual([]);
  });
}

test("under-18 athletes see no target weight or gap", async ({ page, baseURL }) => {
  await signInAthlete(page, baseURL!, { isMinor: true });
  await page.goto("/nutrition");
  await expect(page.getByRole("heading", { level: 1, name: "Weight tracker" })).toBeVisible();
  await expect(page.getByText("7-day average", { exact: true })).toBeVisible();
  await expect(page.getByText("Target", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Target gap", { exact: true })).toHaveCount(0);
});
