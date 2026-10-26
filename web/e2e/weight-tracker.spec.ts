import { expect, test, type Page } from "@playwright/test";
import { isolateFromNetwork } from "./support";

// Nutrition is the weight tracker: the old workspace form, its BMI/weight-source
// plumbing and the "Coming soon" gate are gone. Set WEIGHT_TRACKER_SCREENSHOTS
// to a directory to capture the page and logging sheet at phone and desktop widths.
const shots = process.env.WEIGHT_TRACKER_SCREENSHOTS;

// What the API derives from the log: a calendar 7-day average, the weekly pace,
// the smoothed trend and the plan's own weight-cut band. `legacy` drops the
// fields an older API does not send, since the web app can deploy first.
function derived(isMinor: boolean, empty: boolean, legacy: boolean) {
  const base = { days_until_fight: 19, weight_cut_pct: isMinor ? 0 : 4.6, readiness_flags: [], missing_required_fields: [], foundation_status: "ready",
    rolling_7_day_average_weight: empty ? null : 73.7 };
  if (legacy) return base;
  return { ...base, rolling_7_day_weigh_in_days: empty ? 0 : 3, weekly_pace_kg: empty ? null : -0.6,
    weight_cut_risk_band: isMinor ? "none" : "high", weight_cut_supervision_required: !isMinor,
    bodyweight_trend: empty ? [] : [
      { date: "2026-10-21", scale_weight_kg: 74.1, trend_weight_kg: 74.1 },
      { date: "2026-10-23", scale_weight_kg: 73.6, trend_weight_kg: 73.92 },
      { date: "2026-10-26", scale_weight_kg: 73.4, trend_weight_kg: 73.69 },
    ] };
}

function workspace(isMinor: boolean, empty = false, legacy = false) {
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
      daily_bodyweight_log: empty ? [] : [
        { date: "2026-10-21", weight_kg: 74.1, time: "07:10", is_fasted: true, notes: null },
        { date: "2026-10-23", weight_kg: 73.6, time: "07:05", is_fasted: true, notes: null },
        { date: "2026-10-26", weight_kg: 73.4, time: "07:00", is_fasted: true, notes: "Morning, after toilet" },
      ],
    },
    nutrition_coach_controls: {},
    derived: derived(isMinor, empty, legacy),
  };
}

async function signInAthlete(page: Page, baseURL: string, { isMinor, empty = false, legacy = false }: { isMinor: boolean; empty?: boolean; legacy?: boolean }) {
  await isolateFromNetwork(page, baseURL);
  const key = `sb-${new URL(process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://stub.supabase.co").hostname.split(".")[0]}-auth-token`;
  await page.addInitScript(([key, value]) => localStorage.setItem(key, value), [key, JSON.stringify({
    access_token: "fixture-token", refresh_token: "fixture", token_type: "bearer", expires_at: Math.floor(Date.now() / 1000) + 86400,
    user: { id: "athlete-1", email: "fighter@example.com", aud: "authenticated", role: "authenticated", app_metadata: {}, user_metadata: {} },
  })]);
  const saves: unknown[] = [];
  let current = workspace(isMinor, empty, legacy);
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
  test(`Weight tracker: summary, trend, list and logging sheet (${width}px)`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const saves = await signInAthlete(page, baseURL!, { isMinor: false });
    const shot = async (name: string, fullPage = false) => {
      await page.waitForTimeout(250); // let button colour transitions settle
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (shots) await page.screenshot({ path: `${shots}/${name}-${width}.png`, fullPage });
    };

    await page.goto("/nutrition/bodyweight-log");
    await expect(page).toHaveURL(/\/nutrition$/);
    await expect(page.getByRole("heading", { level: 1, name: "Weight tracker" })).toBeVisible();
    const summary = page.getByRole("region", { name: "Weight summary" });
    await expect(summary.getByText("73.4", { exact: true })).toBeVisible();
    await expect(summary.getByText("3.4 kg", { exact: true })).toBeVisible();
    await expect(summary.getByText("Above target")).toBeVisible();
    await expect(summary.getByText("19", { exact: true })).toBeVisible();
    await expect(summary.getByText("7-day average")).toBeVisible();
    await expect(summary.getByText("73.7", { exact: true })).toBeVisible();
    await expect(summary.getByText("Per week")).toBeVisible();
    await expect(summary.getByText("−0.6 kg", { exact: true })).toBeVisible();
    await expect(page.getByText(/^High-strain weight cut: 4\.6% of your bodyweight to target with 19 days to go\./)).toBeVisible();
    for (const removed of ["BMI", "Weight source", "Nutrition workspace", "COMING SOON"]) {
      await expect(page.getByText(removed, { exact: true })).toHaveCount(0);
    }

    // The trend selects the latest weigh-in; arrow keys step back through it.
    const trend = page.getByRole("region", { name: "Weight trend" });
    const selected = trend.getByLabel("Selected weigh-in");
    await expect(selected).toContainText("73.4 kg");
    await expect(selected).toContainText("−0.2 kg vs previous");
    await expect(trend.getByText("Down 0.7 kg since Wed 21 Oct 2026")).toBeVisible();
    await expect(selected).toContainText("Trend 73.7 kg");
    await expect(trend.getByText("Trend (estimate)")).toBeVisible();
    await trend.getByRole("slider", { name: "Inspect weigh-in" }).focus();
    await page.keyboard.press("ArrowLeft");
    await expect(selected).toContainText("73.6 kg");
    await shot("weight-tracker", true);
    await trend.scrollIntoViewIfNeeded();
    await shot("weight-trend");

    // Rows open the same sheet in edit mode.
    await page.getByRole("region", { name: "Weigh-ins" }).getByRole("button", { name: /Fri 23 Oct 2026/ }).click();
    await expect(page.getByRole("dialog", { name: "Edit weigh-in" })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);

    await summary.getByRole("button", { name: "Log weigh-in" }).click();
    const dialog = page.getByRole("dialog", { name: "Log weigh-in" });
    await expect(dialog.getByLabel("Weight")).toBeFocused();
    await dialog.getByRole("button", { name: "Decrease by 0.1 kg" }).click();
    await expect(dialog.getByLabel("Weight")).toHaveValue("73.3");
    await dialog.getByRole("button", { name: "Fasted" }).click();
    await expect(dialog.getByRole("button", { name: "Fasted" })).toHaveAttribute("aria-pressed", "true");
    await shot("weight-tracker-sheet");
    await dialog.getByRole("button", { name: "Save weigh-in" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(saves).toHaveLength(1);
    await expect(summary.getByText("73.3", { exact: true })).toBeVisible();

    if (width === 1280) {
      const navLink = page.getByRole("link", { name: /Weight tracker/ }).first();
      await expect(navLink).toHaveAttribute("href", "/nutrition");
    }
    expect(errors).toEqual([]);
  });
}

test("under-18 athletes see no target weight or gap", async ({ page, baseURL }) => {
  await signInAthlete(page, baseURL!, { isMinor: true });
  await page.goto("/nutrition");
  await expect(page.getByRole("heading", { level: 1, name: "Weight tracker" })).toBeVisible();
  await expect(page.getByText("7-day average", { exact: true })).toBeVisible();
  await expect(page.locator(".history-screen").getByText(/target/i)).toHaveCount(0);
  await expect(page.getByText(/weight cut:/i)).toHaveCount(0);
});

test("an older API without trend fields still renders the tracker", async ({ page, baseURL }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await signInAthlete(page, baseURL!, { isMinor: false, legacy: true });
  await page.goto("/nutrition");
  const summary = page.getByRole("region", { name: "Weight summary" });
  await expect(summary.getByText("73.4", { exact: true })).toBeVisible();
  await expect(summary.getByText("Per week")).toHaveCount(0);
  await expect(page.getByText(/weight cut:/i)).toHaveCount(0);
  const trend = page.getByRole("region", { name: "Weight trend" });
  await expect(trend.getByRole("slider", { name: "Inspect weigh-in" })).toBeVisible();
  await expect(trend.getByText("Trend (estimate)")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("a first weigh-in starts from an empty state", async ({ page, baseURL }) => {
  await signInAthlete(page, baseURL!, { isMinor: false, empty: true });
  await page.goto("/nutrition");
  await expect(page.getByRole("heading", { name: "No weigh-ins yet" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Weight trend" })).toHaveCount(0);
  await page.getByRole("button", { name: "Log weigh-in" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Save weigh-in" }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toHaveText("Enter your weight in kg.");
});
