import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { isolateFromNetwork } from "./support";
import type { CustomPlan, CustomPlanInput, LibraryEntry } from "../lib/api-schema.generated";

const athlete = "00000000-0000-4000-8000-000000000001";
const storageKey = `sb-${new URL(process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://stub.supabase.co").hostname.split(".")[0]}-auth-token`;
const entries: LibraryEntry[] = ["Medicine Ball Hook Throw", "Standing Cable Punch Simulation"].map((name, index) => ({
  catalogue_id: `exact-training-id-${index}`, name, category: "training", content_type: "strength_power", context: "Strength",
  equipment: [], equipment_state: "known", equipment_requirements: null, focus: [], verified_goals: [], exercise_details: [],
  discovery_match: null, exercise_key: `exercise-key-${index}`, media: null, selection_boundary: "training_validation_required", prescription_allowed: false,
}));

async function setup(page: Page, baseURL: string) {
  await isolateFromNetwork(page, baseURL);
  await page.route("https://fonts.googleapis.com/**", route => route.fulfill({ contentType: "text/css", body: "" }));
  await page.addInitScript(([key, value]) => localStorage.setItem(key, value), [storageKey, JSON.stringify({
    access_token: "athlete-token", refresh_token: "test-refresh", token_type: "bearer", expires_in: 86400,
    expires_at: Math.floor(Date.now() / 1000) + 86400,
    user: { id: athlete, email: "fighter@example.com", aud: "authenticated", role: "authenticated", app_metadata: {}, user_metadata: {} },
  })]);
  const saved = new Map<string, CustomPlan>();
  const mutations: string[] = [];
  let drills = entries;
  if (process.env.CUSTOM_PLAN_TEST_API) {
    const response = await page.request.get(`${process.env.CUSTOM_PLAN_TEST_API}/api/training/library?q=Medicine%20Ball%20Hook%20Throw`, { headers: { Authorization: "Bearer athlete-token" } });
    expect(response.ok()).toBe(true);
    drills = (await response.json()).entries;
    expect(drills.some(entry => entry.name === entries[0].name)).toBe(true);
  }
  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (request.method() !== "GET") mutations.push(url.pathname);
    if (url.pathname === "/api/xp/activity") {
      expect(request.postData()).toBeNull();
    }
    if (url.pathname.startsWith("/api/custom-plans") || url.pathname.startsWith("/api/training/library")) {
      expect(request.headers().authorization).toBe("Bearer athlete-token");
      if (process.env.CUSTOM_PLAN_TEST_API) {
        const response = await page.request.fetch(`${process.env.CUSTOM_PLAN_TEST_API}${url.pathname}${url.search}`, {
          method: request.method(), headers: { Authorization: "Bearer athlete-token", "Content-Type": "application/json" },
          data: request.postData() ?? undefined,
        });
        return route.fulfill({ response });
      }
      if (url.pathname.startsWith("/api/training/library")) {
        if (url.pathname.endsWith("/featured")) return json({ entry: null });
        if (url.pathname.endsWith("/entry")) return json({ ...drills.find(entry => entry.catalogue_id === url.searchParams.get("catalogue_id")),
          source: "exercise_bank.json", source_revision: "source-revision", row_revision: "row-revision", guidance: { Cues: ["Stay controlled."] }, metadata_projection: [] });
        expect(url.searchParams.get("category")).toBe("training");
        const query = url.searchParams.get("q")?.toLowerCase() ?? "";
        const results = drills.filter(entry => entry.name.toLowerCase().includes(query));
        return json({ entries: results, total: results.length, catalogue_total: 2855, offset: 0, limit: 24,
          next_offset: null, revision: "fixture", facets: { type: [{ value: "strength_power", label: "Strength & power", count: 2 }] } });
      }
      const id = url.pathname.split("/")[3];
      if (request.method() === "GET") return json(id ? saved.get(id) : [...saved.values()]);
      if (request.method() === "DELETE") { saved.delete(id); return route.fulfill({ status: 204 }); }
      const body = request.postDataJSON() as CustomPlanInput;
      expect(Object.keys(body).sort()).toEqual(["name", "sessions"]);
      const sessions = (body.sessions ?? []).map(session => ({ ...session, weekday: session.weekday ?? null,
        exercises: (session.exercises ?? []).map(exercise => {
          expect(Object.keys(exercise).sort()).toEqual(["catalogue_id", "dose", "id"]);
          const entry = drills.find(entry => entry.catalogue_id === exercise.catalogue_id)!;
          expect(entry).toBeTruthy();
          const dose = { mode: "reps" as const, sets: null, reps: null, duration_seconds: null, rest_seconds: null, load_or_intensity: null, ...exercise.dose };
          return { ...exercise, dose, snapshot: { ...entry, category: "training" as const, source: "exercise_bank.json", source_revision: "source-revision", row_revision: "row-revision" },
            incomplete: dose.mode === "reps" ? !dose.sets || !dose.reps : !dose.duration_seconds };
        }),
      }));
      const plan: CustomPlan = { id: id || crypto.randomUUID(), name: body.name, sessions, kind: "self_directed",
        incomplete: !sessions.length || sessions.some(session => !session.exercises.length || session.exercises.some(exercise => exercise.incomplete)),
        created_at: "2026-10-11T12:00:00Z", updated_at: "2026-10-11T12:00:00Z" };
      saved.set(plan.id, plan);
      return json(plan, id ? 200 : 201);
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
    return json({ notifications: [], unread_count: 0, level: 1, total_xp: 0 });
  });
  return { mutations };
}

for (const width of [320, 390, 1280]) {
  test(`Build, preview, dose, save, reload, edit and delete a self-directed plan (${width}px)`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height: 844 });
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("console", message => {
      // This journey deliberately starts with no generated camp. Its lookup is
      // expected to return 404; every other console error still fails the test.
      if (message.type() === "error" && !(message.text().includes("404") && message.location().url.endsWith("/api/plans/active"))) {
        errors.push(`${message.text()} ${message.location().url}`);
      }
    });
    const { mutations } = await setup(page, baseURL!);
    await page.goto("/plans");
    await page.getByRole("link", { name: "Build My Own Plan" }).click();
    await expect(page.getByRole("heading", { name: "MY TRAINING PLAN", exact: true })).toBeVisible();
    const planName = `Weekly strength ${width}`;
    await page.getByLabel("Plan name", { exact: true }).fill(planName);
    await page.getByRole("button", { name: "+ Add Session", exact: true }).click();
    await page.getByLabel("Session 1 name", { exact: true }).fill("Strength");
    await page.getByLabel("Session 1 Day", { exact: true }).selectOption("Monday");
    await page.getByRole("button", { name: "+ Add Exercise", exact: true }).click();
    await expect(page.getByRole("group", { name: "Library category", exact: true })).toHaveCount(0);
    await page.getByLabel("Search drills", { exact: true }).fill(entries[0].name);
    await page.getByRole("list", { name: "Drill results", exact: true }).getByRole("button").filter({ hasText: entries[0].name }).click();
    if (!process.env.CUSTOM_PLAN_TEST_API) await expect(page.getByRole("dialog")).toContainText("Stay controlled.");
    await expect(page.getByRole("button", { name: "Add to Session", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Add to Session", exact: true }).click();
    await expect(page.getByLabel("Plan name", { exact: true })).toHaveValue(planName);
    await expect(page.getByLabel("Session 1 name", { exact: true })).toHaveValue("Strength");
    await expect(page.getByText("Incomplete dose", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Save Plan", exact: true }).click();
    await expect(page.getByRole("status").filter({ hasText: "Draft saved" })).toBeVisible();
    await page.getByLabel(`${entries[0].name} Sets`, { exact: true }).fill("3");
    await page.getByLabel(`${entries[0].name} Reps`, { exact: true }).fill("5");
    await page.getByLabel(`${entries[0].name} Rest (sec)`, { exact: true }).fill("90");
    await page.getByText("Load / intensity", { exact: true }).click();
    await page.getByLabel(`${entries[0].name} Load or intensity`, { exact: true }).fill("RPE 7");
    await page.getByRole("button", { name: "+ Add Exercise", exact: true }).click();
    await page.getByLabel("Search drills", { exact: true }).fill(entries[1].name);
    await page.getByRole("list", { name: "Drill results", exact: true }).getByRole("button").filter({ hasText: entries[1].name }).click();
    await page.getByRole("button", { name: "Add to Session", exact: true }).click();
    await page.getByLabel(`${entries[1].name} Sets`, { exact: true }).fill("3");
    await page.getByLabel(`${entries[1].name} Reps`, { exact: true }).fill("8");
    await page.getByRole("button", { name: `Move ${entries[1].name} up`, exact: true }).click();
    await page.getByRole("button", { name: "Save Plan", exact: true }).click();
    await expect(page.getByRole("status").filter({ hasText: "Plan saved." })).toBeVisible();
    await page.reload();
    await page.getByRole("region", { name: "Saved custom plans", exact: true }).getByRole("button", { name: planName, exact: true }).click();
    await expect(page.getByLabel(`${entries[0].name} Sets`, { exact: true })).toHaveValue("3");
    await expect(page.getByLabel(`${entries[0].name} Reps`, { exact: true })).toHaveValue("5");
    await expect(page.getByLabel("Session 1 Day", { exact: true })).toHaveValue("Monday");
    const exercises = page.getByRole("region", { name: "Session 1", exact: true }).getByRole("listitem");
    await expect(exercises.first()).toContainText(entries[1].name);
    await expect(exercises.last()).toContainText(entries[0].name);
    await page.getByRole("button", { name: `Remove ${entries[1].name}`, exact: true }).click();
    await expect(exercises).toHaveCount(1);
    await page.getByLabel(`${entries[0].name} Dose`, { exact: true }).selectOption("duration");
    await page.getByLabel(`${entries[0].name} Duration (sec)`, { exact: true }).fill("30");
    await expect(page.getByLabel(`${entries[0].name} Reps`, { exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "Save Plan", exact: true }).click();
    await expect(page.getByRole("status").filter({ hasText: "Plan saved." })).toBeVisible();
    await page.screenshot({ path: test.info().outputPath(`custom-builder-${width}.png`), animations: "disabled", fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect((await new AxeBuilder({ page }).include('[aria-label="Custom training plan builder"]').analyze()).violations).toEqual([]);
    await page.getByRole("button", { name: "Delete plan", exact: true }).click();
    await page.getByRole("button", { name: "Confirm delete", exact: true }).click();
    await expect(page.getByRole("region", { name: "Saved custom plans", exact: true }).getByRole("button", { name: planName, exact: true })).toHaveCount(0);
    expect(mutations.length).toBeGreaterThan(0);
    // The app shell sends its existing body-free activity heartbeat on hydration.
    expect(mutations.filter(path => path !== "/api/xp/activity")).toEqual(expect.arrayContaining(["/api/custom-plans"]));
    expect(mutations.filter(path => path !== "/api/xp/activity").every(path => path.startsWith("/api/custom-plans")), JSON.stringify(mutations)).toBe(true);
    expect(errors).toEqual([]);
  });
}
