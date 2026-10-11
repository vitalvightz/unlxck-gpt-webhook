import { expect, test, type Page } from "@playwright/test";
import { blankDose } from "../lib/custom-plan-dose";
import AxeBuilder from "@axe-core/playwright";
import { isolateFromNetwork } from "./support";
import type { CustomPlan, CustomPlanInput, LibraryEntry } from "../lib/api-schema.generated";

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: "wait" });
});

const athlete = "00000000-0000-4000-8000-000000000001";
const storageKey = `sb-${new URL(process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://stub.supabase.co").hostname.split(".")[0]}-auth-token`;
const entries: LibraryEntry[] = ["Medicine Ball Hook Throw", "Standing Cable Punch Simulation"].map((name, index) => ({
  catalogue_id: `exact-training-id-${index}`,
  name,
  category: "training",
  content_type: "strength_power",
  context: "Strength",
  equipment: [],
  equipment_state: "known",
  equipment_requirements: null,
  focus: [],
  verified_goals: [],
  exercise_details: [],
  discovery_match: null,
  exercise_key: `exercise-key-${index}`,
  media: null,
  selection_boundary: "training_validation_required",
  prescription_allowed: false,
}));

async function setup(page: Page, baseURL: string) {
  await isolateFromNetwork(page, baseURL);
  await page.route("https://fonts.googleapis.com/**", (route) => route.fulfill({ contentType: "text/css", body: "" }));
  await page.addInitScript(
    ([key, value]) => localStorage.setItem(key, value),
    [
      storageKey,
      JSON.stringify({
        access_token: "athlete-token",
        refresh_token: "test-refresh",
        token_type: "bearer",
        expires_in: 86400,
        expires_at: Math.floor(Date.now() / 1000) + 86400,
        user: {
          id: athlete,
          email: "fighter@example.com",
          aud: "authenticated",
          role: "authenticated",
          app_metadata: {},
          user_metadata: {},
        },
      }),
    ],
  );
  const saved = new Map<string, CustomPlan>();
  const mutations: string[] = [];
  let drills = entries;
  if (process.env.CUSTOM_PLAN_TEST_API) {
    const response = await page.request.get(
      `${process.env.CUSTOM_PLAN_TEST_API}/api/training/library?q=Medicine%20Ball%20Hook%20Throw`,
      { headers: { Authorization: "Bearer athlete-token" } },
    );
    expect(response.ok()).toBe(true);
    drills = (await response.json()).entries;
    expect(drills.some((entry) => entry.name === entries[0].name)).toBe(true);
  }
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const json = (body: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    if (request.method() !== "GET") mutations.push(url.pathname);
    if (url.pathname === "/api/xp/activity") {
      expect(request.postData()).toBeNull();
    }
    if (url.pathname.startsWith("/api/custom-plans") || url.pathname.startsWith("/api/training/library")) {
      expect(request.headers().authorization).toBe("Bearer athlete-token");
      if (process.env.CUSTOM_PLAN_TEST_API) {
        const response = await page.request.fetch(`${process.env.CUSTOM_PLAN_TEST_API}${url.pathname}${url.search}`, {
          method: request.method(),
          headers: {
            Authorization: "Bearer athlete-token",
            "Content-Type": "application/json",
          },
          data: request.postData() ?? undefined,
        });
        return route.fulfill({ response });
      }
      if (url.pathname.startsWith("/api/training/library")) {
        if (url.pathname.endsWith("/featured")) return json({ entry: null });
        if (url.pathname.endsWith("/entry"))
          return json({
            ...drills.find((entry) => entry.catalogue_id === url.searchParams.get("catalogue_id")),
            source: "exercise_bank.json",
            source_revision: "source-revision",
            row_revision: "row-revision",
            guidance: { Cues: ["Stay controlled."] },
            metadata_projection: [],
          });
        expect(url.searchParams.get("category")).toBe("training");
        const query = url.searchParams.get("q")?.toLowerCase() ?? "";
        const results = drills.filter((entry) => entry.name.toLowerCase().includes(query));
        return json({
          entries: results,
          total: results.length,
          catalogue_total: 2855,
          offset: 0,
          limit: 24,
          next_offset: null,
          revision: "fixture",
          facets: {
            type: [{ value: "strength_power", label: "Strength & power", count: 2 }],
          },
        });
      }
      if (url.pathname.endsWith("/source-suggestion"))
        return json({
          dose: { ...blankDose("intervals"), rounds: 5, work_seconds: 300, rest_seconds: 30 },
          original: "5x5min, 30s rest",
          source: "conditioning_bank.json",
          source_revision: "current-source",
          row_revision: "current-row",
        });
      const id = url.pathname.split("/")[3];
      if (request.method() === "GET") return json(id ? saved.get(id) : [...saved.values()]);
      if (request.method() === "DELETE") {
        saved.delete(id);
        return route.fulfill({ status: 204 });
      }
      const body = request.postDataJSON() as CustomPlanInput;
      expect(Object.keys(body).sort()).toEqual(["name", "sessions"]);
      const sessions = (body.sessions ?? []).map((session) => ({
        ...session,
        weekday: session.weekday ?? null,
        exercises: (session.exercises ?? []).map((exercise) => {
          const dose = { ...blankDose(), ...exercise.dose };
          const incomplete =
            dose.mode === "reps"
              ? !dose.sets || !dose.reps
              : dose.mode === "duration"
                ? !dose.duration_seconds
                : dose.mode === "intervals"
                  ? !dose.rounds || !dose.work_seconds || dose.rest_seconds == null
                  : !dose.prescription;
          if (exercise.origin === "manual")
            return {
              ...exercise,
              equipment: exercise.equipment ?? null,
              notes: exercise.notes ?? null,
              media_id: exercise.media_id ?? null,
              dose,
              incomplete,
            };
          const entry = drills.find((entry) => entry.catalogue_id === exercise.catalogue_id)!;
          expect(entry).toBeTruthy();
          return {
            ...exercise,
            origin: "catalogue" as const,
            dose,
            incomplete,
            snapshot: {
              ...entry,
              category: "training" as const,
              source: "exercise_bank.json",
              source_revision: "source-revision",
              row_revision: "row-revision",
            },
          };
        }),
      }));
      const plan: CustomPlan = {
        id: id || crypto.randomUUID(),
        name: body.name,
        sessions,
        kind: "self_directed",
        incomplete:
          !sessions.length ||
          sessions.some(
            (session) => !session.exercises.length || session.exercises.some((exercise) => exercise.incomplete),
          ),
        created_at: "2026-10-11T12:00:00Z",
        updated_at: "2026-10-11T12:00:00Z",
      };
      saved.set(plan.id, plan);
      return json(plan, id ? 200 : 201);
    }
    if (url.pathname === "/api/me")
      return json({
        profile: {
          athlete_id: athlete,
          email: "fighter@example.com",
          full_name: "Carlos",
          role: "athlete",
          access_status: "approved",
          technical_style: ["boxing"],
          tactical_style: [],
          stance: "orthodox",
          professional_status: "professional",
          record: "",
          athlete_timezone: "Europe/London",
          athlete_locale: "en",
          appearance_mode: "dark",
          nutrition_profile: {},
          date_of_birth: "1995-01-01",
          meets_minimum_age: true,
          is_minor: false,
          terms_accepted: true,
          health_consent_granted: true,
          private_trial_ack_at: "2026-01-01T12:00:00Z",
        },
        plan_count: 0,
        latest_plan: null,
        latest_intake: null,
        username_rate_limit: {},
      });
    if (url.pathname === "/api/plans/active") return json({ detail: "No active plan" }, 404);
    if (url.pathname === "/api/plans") return json([]);
    return json({ notifications: [], unread_count: 0, level: 1, total_xp: 0 });
  });
  return { mutations, saved };
}

for (const width of [320, 390, 1280]) {
  test(`Saved links, mixed exercises and compact doses (${width}px)`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height: 844 });
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const { mutations } = await setup(page, baseURL!);
    await page.goto("/plans");
    await page.getByRole("link", { name: "Build My Own Plan" }).click();
    await page.getByLabel("Plan name", { exact: true }).fill(`Weekly strength ${width}`);
    await page.getByRole("button", { name: "+ Add Session", exact: true }).click();
    await page.getByRole("button", { name: "Edit session 1", exact: true }).click();
    await page.getByLabel("Session name", { exact: true }).fill("Strength");
    await page.getByLabel("Day", { exact: true }).selectOption("Monday");
    await page.getByRole("button", { name: "Done", exact: true }).click();
    await page.getByRole("button", { name: "Add from library", exact: true }).click();
    await page.getByLabel("Search drills", { exact: true }).fill(entries[0].name);
    await page
      .getByRole("list", { name: "Drill results" })
      .getByRole("button")
      .filter({ hasText: entries[0].name })
      .click();
    await page.getByRole("button", { name: "Add to Session", exact: true }).click();
    await expect(page.getByLabel("Sets", { exact: true })).toHaveCount(0);
    await page
      .getByRole("button", {
        name: `Edit dose for ${entries[0].name}`,
        exact: true,
      })
      .click();
    if (!process.env.CUSTOM_PLAN_TEST_API) {
      await page.getByRole("button", { name: "Suggested format", exact: true }).click();
      await expect(page.getByRole("button", { name: "Use source suggestion", exact: true })).toBeVisible();
      await expect(page.getByLabel("Sets", { exact: true })).toHaveValue("");
      await page.getByRole("button", { name: "Use source suggestion", exact: true }).click();
      await expect(page.getByLabel("Rounds", { exact: true })).toHaveValue("5");
      await expect(page.getByLabel("Work duration", { exact: true })).toHaveValue("5");
      await page.getByLabel("Dose format").selectOption("reps");
    }
    await page.getByLabel("Sets", { exact: true }).fill("4");
    await page.getByLabel("Reps", { exact: true }).fill("8");
    await page.getByLabel("Rest (sec)", { exact: true }).fill("120");
    await page.getByLabel("Load or intensity", { exact: true }).fill("80 kg");
    await page.getByRole("button", { name: "Done", exact: true }).click();
    await page.getByRole("button", { name: "Create my exercise", exact: true }).click();
    await page.getByLabel("Exercise name", { exact: true }).fill("My bag rounds");
    await page.getByLabel("equipment (optional)", { exact: true }).fill("Heavy bag");
    await page.getByLabel("notes (optional)", { exact: true }).fill("My own practice");
    await page.getByLabel("Dose format").selectOption("intervals");
    await page.getByLabel("Rounds", { exact: true }).fill("5");
    await page.getByLabel("Work duration unit").selectOption("60");
    await page.getByLabel("Work duration", { exact: true }).fill("5");
    await page.getByLabel("Rest between (sec)").fill("30");
    await page.getByRole("button", { name: "Add exercise", exact: true }).click();
    await page.getByRole("button", { name: "Edit dose for My bag rounds", exact: true }).click();
    await page.getByLabel("Position in session").selectOption("0");
    await page.getByRole("button", { name: "Done", exact: true }).click();
    await page.getByRole("button", { name: "Save Plan", exact: true }).click();
    await expect(page).toHaveURL(/custom\?plan=/);
    await expect(page.getByText("Unsaved changes", { exact: true })).toHaveCount(0);
    await page.getByRole("link", { name: /Saved custom plans/ }).click();
    const card = page
      .getByRole("region", { name: "Saved custom plans" })
      .getByRole("link")
      .filter({ hasText: `Weekly strength ${width}` });
    await card.scrollIntoViewIfNeeded();
    await card.click();
    await expect(page.getByRole("heading", { level: 1 })).toBeInViewport();
    await expect(page.getByRole("heading", { level: 1 })).toBeFocused();
    await page.reload();
    const exercises = page.getByRole("region", { name: "Session 1", exact: true }).getByRole("listitem");
    await expect(exercises.first()).toContainText("My bag rounds");
    await expect(exercises.last()).toContainText("4 × 8 · 80 kg · rest 120s");
    await expect(page.getByText("Monday", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Edit dose for My bag rounds" }).click();
    await expect(page.getByLabel("Work duration", { exact: true })).toHaveValue("5");
    await page.getByLabel("Exercise name").fill("My renamed rounds");
    page.once("dialog", (dialog) => dialog.dismiss());
    await page.goBack();
    await expect(page.getByLabel("Exercise name")).toHaveValue("My renamed rounds");
    await page.getByRole("button", { name: "Done", exact: true }).click();
    page.once("dialog", (dialog) => dialog.dismiss());
    await page.getByRole("link", { name: /Saved custom plans/ }).click();
    await expect(page.getByLabel("Plan name")).toBeVisible();
    page.once("dialog", (dialog) => dialog.dismiss());
    await page.goBack();
    await expect(page.getByText("My renamed rounds", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Save Plan", exact: true }).click();
    await expect(page.getByText("Unsaved changes", { exact: true })).toHaveCount(0);
    await page.goBack();
    await expect(page).toHaveURL(/\/plans(?:#custom-plans)?$/);
    await page.goForward();
    await expect(page.getByText("My renamed rounds", { exact: true })).toBeVisible();
    await page.screenshot({
      path: test.info().outputPath(`custom-builder-${width}.png`),
      animations: "disabled",
      fullPage: true,
    });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const saveBounds = await page.getByRole("button", { name: "Save Plan", exact: true }).boundingBox();
    expect(saveBounds!.y + saveBounds!.height).toBeLessThan(width < 768 ? 780 : 844);
    expect(
      (await new AxeBuilder({ page }).include('[aria-label="Custom training plan builder"]').analyze()).violations,
    ).toEqual([]);
    page.once("dialog", (dialog) => dialog.accept());
    await page.getByRole("button", { name: "Delete plan", exact: true }).click();
    await expect(
      page
        .getByRole("region", { name: "Saved custom plans" })
        .getByRole("link")
        .filter({ hasText: `Weekly strength ${width}` }),
    ).toHaveCount(0);
    expect(
      mutations.filter((path) => path !== "/api/xp/activity").every((path) => path.startsWith("/api/custom-plans")),
    ).toBe(true);
    expect(errors).toEqual([]);
  });
}

for (const width of [320, 390, 1280]) {
  test(`Private video clip selection, playback and persistence (${width}px)`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height: 844 });
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    const { saved } = await setup(page, baseURL!);
    const media = { id: "00000000-0000-4000-8000-000000000099", provider: "youtube", video_id: "abcdefghijk",
      start_s: 10, end_s: 25, asset_id: null, channel_title: "Coach", orientation: "landscape", url: null };
    let verified = false;
    await page.route("**/api/private-media/**", async route => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/settings")) return route.fulfill({ json: { uploads_available: false, youtube_available: true } });
      if (path.endsWith("/youtube")) {
        expect(route.request().postDataJSON()).toEqual({ url: "https://youtube.com/watch?v=abcdefghijk", start_s: 10, end_s: 25 });
        verified = true;
      }
      return route.fulfill({ json: media });
    });
    // Deterministic offline IFrame API: verify the existing player receives the selected segment.
    await page.route("https://www.youtube.com/iframe_api", route => route.fulfill({ contentType: "text/javascript", body: `
      window.YT = { PlayerState: { PLAYING: 1, PAUSED: 2, ENDED: 0 }, Player: function(target, options) {
        window.__clipOptions = options;
        let time = options.playerVars.start;
        this.playVideo = () => options.events.onStateChange({ data: 1, target: this });
        this.pauseVideo = () => options.events.onStateChange({ data: 2, target: this });
        this.seekTo = value => { time = value; window.__clipSeek = value; window.__clipTime = value; };
        this.getCurrentTime = () => window.__clipTime ?? time;
        this.setPlaybackRate = () => {}; this.mute = () => {}; this.unMute = () => {}; this.destroy = () => {};
        setTimeout(() => options.events.onReady({ target: this }), 0);
      }}; window.onYouTubeIframeAPIReady?.();
    ` }));
    await page.goto("/plans/custom");
    await page.getByRole("button", { name: "+ Add Session", exact: true }).click();
    await page.getByRole("button", { name: "Create my exercise", exact: true }).click();
    await page.getByLabel("Exercise name", { exact: true }).fill("My defensive drill");
    await page.getByRole("button", { name: "Add video (optional)", exact: true }).click();
    const sheet = page.getByRole("dialog", { name: "Demonstration video", exact: true });
    await expect(sheet.getByRole("button", { name: "Upload video", exact: true })).toBeDisabled();
    await sheet.getByRole("button", { name: "YouTube link", exact: true }).click();
    await sheet.getByLabel("YouTube link", { exact: true }).fill("https://youtube.com/watch?v=abcdefghijk");
    await sheet.getByLabel("Start (seconds)").fill("10");
    await sheet.getByLabel("End (seconds)").fill("50");
    await sheet.getByRole("button", { name: "Preview clip", exact: true }).click();
    await expect(sheet.getByRole("alert")).toContainText("between 1 and 30 seconds");
    expect(verified).toBe(false);
    await sheet.getByLabel("End (seconds)").fill("25");
    await sheet.getByRole("button", { name: "Preview clip", exact: true }).click();
    await sheet.getByRole("button", { name: "Play My defensive drill demo", exact: true }).click();
    await expect(sheet.getByRole("button", { name: "Pause", exact: true })).toBeVisible();
    expect(await page.evaluate(() => {
      const options = (window as unknown as { __clipOptions: { host: string; playerVars: { start: number; end: number; playsinline: number } } }).__clipOptions;
      return { host: options.host, start: options.playerVars.start, end: options.playerVars.end, inline: options.playerVars.playsinline };
    })).toEqual({ host: "https://www.youtube-nocookie.com", start: 10, end: 25, inline: 1 });
    await sheet.getByRole("button", { name: "Replay", exact: true }).click();
    expect(await page.evaluate(() => (window as unknown as { __clipSeek: number }).__clipSeek)).toBe(10);
    await page.evaluate(() => { (window as unknown as { __clipTime: number }).__clipTime = 25; });
    await expect.poll(() => page.evaluate(() => (window as unknown as { __clipTime: number }).__clipTime)).toBe(10);
    expect(await sheet.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
    if (width >= 1024) {
      const settings = await sheet.getByText("Optional · Up to 30 seconds · Private", { exact: true }).boundingBox();
      const preview = await sheet.getByRole("button", { name: "Use video", exact: true }).boundingBox();
      expect(preview!.x).toBeGreaterThan(settings!.x + settings!.width);
      expect((await sheet.boundingBox())!.width).toBe(720);
    }
    await page.screenshot({ path: `${process.env.TEMP ?? "/tmp"}/unlxck-private-video-${width}.png`, fullPage: false });
    await sheet.getByRole("button", { name: "Use video", exact: true }).click();
    await page.getByRole("button", { name: "Add exercise", exact: true }).click();
    if (width >= 1024) {
      await page.getByRole("button", { name: "+ Add Session", exact: true }).click();
      const first = await page.getByRole("region", { name: "Session 1", exact: true }).boundingBox();
      const second = await page.getByRole("region", { name: "Session 2", exact: true }).boundingBox();
      expect(second!.x).toBeGreaterThan(first!.x + first!.width);
      expect(second!.y).toBe(first!.y);
      await page.screenshot({ path: `${process.env.TEMP ?? "/tmp"}/unlxck-private-builder-${width}.png`, fullPage: true });
    }
    await page.getByRole("button", { name: "Save Plan", exact: true }).click();
    await expect(page).toHaveURL(/custom\?plan=/);
    expect([...saved.values()][0].sessions[0].exercises[0]).toMatchObject({ origin: "manual", media_id: media.id });
    await page.reload();
    await page.getByRole("button", { name: "Edit dose for My defensive drill", exact: true }).click();
    await expect(page.getByRole("button", { name: "Replace video", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Remove video", exact: true }).click();
    await expect(page.getByRole("button", { name: "Add video (optional)", exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });
}

test("Saved-plan failures are visible and retryable", async ({ page, baseURL }) => {
  await setup(page, baseURL!);
  const id = "00000000-0000-4000-8000-000000000099";
  await page.route(`**/api/custom-plans/${id}`, (route) =>
    route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Custom plan not found." }),
    }),
  );
  await page.goto(`/plans/custom?plan=${id}`);
  await expect(page.getByRole("alert").filter({ hasText: "Custom plan not found" })).toContainText(
    "Custom plan not found",
  );
  await expect(page.getByRole("button", { name: "Retry opening plan" })).toBeVisible();
  await expect(page.getByLabel("Plan name")).toHaveCount(0);
  await page.route(`**/api/custom-plans/${id}`, (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id,
        name: "Demo Plan",
        kind: "self_directed",
        sessions: [],
        incomplete: true,
        created_at: "2026-10-11T12:00:00Z",
        updated_at: "2026-10-11T12:00:00Z",
      }),
    }),
  );
  await page.getByRole("button", { name: "Retry opening plan" }).click();
  await expect(page.getByRole("heading", { name: "Demo Plan", exact: true })).toBeVisible();
  await expect(page.getByRole("alert").filter({ hasText: "Custom plan not found" })).toHaveCount(0);
  await page.route("**/api/custom-plans", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Custom plans temporarily unavailable." }),
    }),
  );
  await page.goto("/plans");
  await expect(page.getByRole("region", { name: "Saved custom plans" }).getByRole("alert")).toContainText(
    "temporarily unavailable",
  );
  await expect(page.getByRole("button", { name: "Retry custom plans" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Build My Own Plan" })).toBeVisible();
  await page.route("**/api/custom-plans", (route) => route.fulfill({ contentType: "application/json", body: "[]" }));
  await page.getByRole("button", { name: "Retry custom plans" }).click();
  await expect(page.getByText("No saved custom plans yet. Build your own training week.")).toBeVisible();
});

for (const width of [390, 1280]) {
  test(`Sessions stay in calendar order before save and after reopening (${width}px)`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height: 844 });
    const { saved } = await setup(page, baseURL!);
    await page.goto('/plans/custom');
    const days = ['Sunday', 'Friday', 'Monday', 'Wednesday', 'Tuesday', 'Thursday', 'Saturday', 'Monday', null];
    for (const [index, day] of days.entries()) {
      await page.getByRole('button', { name: '+ Add Session', exact: true }).click();
      await page.getByRole('button', { name: `Edit session ${index + 1}`, exact: true }).click();
      await page.getByLabel('Session name', { exact: true }).fill(`Day ${index}`);
      await page.getByLabel('Day', { exact: true }).selectOption(day ?? '');
      await page.getByRole('button', { name: 'Done', exact: true }).click();
    }
    const expected = ['Day 2', 'Day 7', 'Day 4', 'Day 3', 'Day 5', 'Day 1', 'Day 6', 'Day 0', 'Day 8'];
    const names = page.getByRole('region', { name: /^Session \d+$/ }).getByRole('heading', { level: 2 });
    await expect(names).toHaveText(expected);
    await page.getByRole('button', { name: 'Save Plan', exact: true }).click();
    await expect(page).toHaveURL(/custom\?plan=/);
    expect([...saved.values()][0].sessions.map(session => session.name)).toEqual(expected);
    await page.reload();
    await expect(names).toHaveText(expected);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
