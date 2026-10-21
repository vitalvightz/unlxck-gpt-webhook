import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";
import fixtures from "./fixtures/rehab-today.json";
import { isolateFromNetwork } from "./support";

// Synthetic payloads exported from GET /api/today, not hand-authored eligibility.
async function setup(page: Page, baseURL: string, name: "chest" | "achilles", videoId?: string) {
  await isolateFromNetwork(page, baseURL);
  const { view, profile: sourceProfile } = structuredClone(fixtures[name]);
  const profile = { ...sourceProfile, profile: { ...sourceProfile.profile, private_trial_ack_at: "2026-10-05T12:00:00Z" } };
  const now = new Date("2026-10-05T12:05:00Z");
  await page.clock.setFixedTime(now);
  const key = `sb-${new URL(process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://stub.supabase.co").hostname.split(".")[0]}-auth-token`;
  await page.addInitScript(([key, value]) => localStorage.setItem(key, value), [key, JSON.stringify({
    access_token: "athlete-token", refresh_token: "fixture", token_type: "bearer", expires_at: now.getTime() / 1000 + 86400,
    user: { id: profile.profile.athlete_id, email: "fixture@example.com", aud: "authenticated", role: "authenticated", app_metadata: {}, user_metadata: {} },
  })]);
  const block = view.live_prescription.session.blocks[0];
  if (videoId) Object.assign(view.exercise_media, { [`exercise:${block.exercise_key}`]: {
    provider: "youtube", video_id: videoId, start_s: 0, source: "curated",
  } });
  const writes: Record<string, unknown>[] = [];
  await page.route("**/api/**", async route => {
    const request = route.request(); const url = new URL(request.url());
    const json = (body: unknown, status = 200) => route.fulfill({ status, json: body });
    if (url.pathname === "/api/me") return json(profile);
    if (url.pathname === "/api/today") return json(view);
    if (url.pathname === `/api/plans/${view.active_plan.id}`) return json({
      plan_id: view.active_plan.id, status: "ready", created_at: "2026-10-05T12:00:00Z", outputs: {
        structured_plan: { weeks: [{ week_index: 1, phase_label: "GPP", days: [{ date: view.today.training_day, weekday: "Mon", sessions: [view.live_prescription.session] }] }] },
      },
    });
    if (url.pathname === "/api/today/session-completion") {
      const payload = request.postDataJSON(); writes.push(payload);
      view.today.completion_status = payload.status;
      Object.assign(view.live_prescription.session, { completion_status: payload.status });
      if (payload.status === "done") view.open_injuries[0].rehab_decision.schedule.state = "already_completed";
      return json({ completion: { ...payload, training_day: view.today.training_day }, completion_status: payload.status,
        landing_session_state: "session_done", rehab_response_prompts: [] }, 201);
    }
    if (url.pathname === "/api/training/history") return json({ sessions: [] });
    if (/session-completions|sparring-logs|exercise-logs|pending/.test(url.pathname)) return json({ completions: [], logs: [], response_sets: [] });
    if (url.pathname === "/api/plans") return json([]);
    return json({});
  });
  const errors: string[] = []; page.on("pageerror", error => errors.push(error.message));
  await page.goto("/today");
  await expect(page.getByRole("button", { name: block.display_name, exact: false }).first()).toBeVisible();
  return { block, view, writes, errors };
}

async function shot(page: Page, filename: string) {
  const dir = process.env.REHAB_QA_DIR;
  if (dir) { mkdirSync(dir, { recursive: true }); await page.screenshot({ path: path.join(dir, filename), fullPage: false, animations: "disabled" }); }
}

for (const width of [375, 1280]) {
  test(`chest RESTORE explains unpublished LOAD without impossible unlock instructions at ${width}px`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width, height: 844 });
    const { block, errors } = await setup(page, baseURL!, "chest");
    await expect(page.locator(".today-injury-summary-row")).toBeVisible();
    await expect(page.locator(".today-injury-summary-row")).toContainText("LOAD exercises aren’t available for this injury in UNLXCK yet.");
    await page.getByRole("button", { name: block.display_name, exact: false }).first().click();
    const detail = page.getByRole("dialog");
    await expect(detail).toContainText("Go at your own pace");
    await expect(detail).toContainText("No equipment needed");
    await expect(detail).toContainText("Demo not assigned");
    await expect(detail.locator("iframe, .sp-block-stats")).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await shot(page, `after-chest-exercise-${width}.png`);
    await page.keyboard.press("Escape");
    await page.locator(".today-injury-summary-row").click();
    await page.getByRole("button", { name: /Load · Unavailable in UNLXCK/ }).click();
    await expect(page.getByRole("dialog")).toContainText("LOAD exercises aren’t available");
    await expect(page.getByRole("dialog")).not.toContainText(/Complete your|Confirm what|unlock|Closed/);
    await shot(page, `after-chest-progression-${width}.png`);
    expect(errors).toEqual([]);
    await expect(page).toHaveURL(/\/today$/);
    await expect(page).not.toHaveTitle("");
  });
}

test("published Achilles LOAD uses the shared embed and completes with the existing payload on mobile", async ({ page, baseURL }) => {
  await page.setViewportSize({ width: 375, height: 844 });
  const { block, view, writes, errors } = await setup(page, baseURL!, "achilles", "AAAAAAAAAAA");
  // Deterministic IFrame API stand-in: no unrelated real video is fetched.
  await page.evaluate(() => {
    (window as unknown as { YT: unknown }).YT = { PlayerState: { PLAYING: 1, PAUSED: 2, ENDED: 0 },
      Player: class {
        constructor(target: HTMLElement, options: { host: string; videoId: string; events: { onReady: (e: unknown) => void; onStateChange: (e: unknown) => void; onError: () => void } }) {
          const frame = document.createElement("iframe"); frame.title = "Rehab demo fixture";
          frame.dataset.videoId = options.videoId; frame.dataset.host = options.host; target.replaceWith(frame);
          Object.assign(window, { rehabDemoError: options.events.onError });
          queueMicrotask(() => { options.events.onReady({ target: this }); options.events.onStateChange({ target: this, data: 1 }); });
        }
        playVideo() {} destroy() {} getCurrentTime() { return 0; } seekTo() {} setPlaybackRate() {} mute() {} unMute() {}
      },
    };
  });
  await page.getByRole("button", { name: block.display_name, exact: false }).first().click();
  const detail = page.getByRole("dialog");
  await expect(detail).toContainText("1 × 10");
  await expect(detail).toContainText("Bodyweight only");
  await expect(detail).toContainText("Floor level only");
  await expect(detail).toContainText("does not provide training or contact clearance");
  await detail.evaluate(element => { element.scrollTop = 0; });
  await shot(page, "after-achilles-prescription-375.png");
  await detail.getByRole("button", { name: `Play ${block.display_name} demo` }).click();
  await expect(detail.locator("iframe")).toHaveAttribute("data-video-id", "AAAAAAAAAAA");
  await expect(detail.locator("iframe")).toHaveAttribute("data-host", "https://www.youtube-nocookie.com");
  await detail.evaluate(element => { element.scrollTop = 0; });
  await shot(page, "after-achilles-demo-375.png");
  await page.evaluate(() => (window as unknown as { rehabDemoError: () => void }).rehabDemoError());
  await expect(detail).toContainText("Video unavailable here. Use the cues below.");
  await expect(detail.getByRole("link", { name: "Watch on YouTube" })).toHaveAttribute("href", "https://www.youtube.com/watch?v=AAAAAAAAAAA");
  await expect(detail).toContainText("Floor level only");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.keyboard.press("Escape");
  await page.getByRole("group", { name: "Did you complete your rehab?" }).getByRole("button", { name: "Completed", exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toMatchObject({ status: "done", rehab_tracking: "injury_checkin", rehab_performance: "done_as_shown",
    prescription_revision: view.live_prescription.revision, session_id: view.live_prescription.session.session_id });
  await expect(page.getByRole("group", { name: "Did you complete your rehab?" })).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("an invalid demo leaves the actual Today exercise usable", async ({ page, baseURL }) => {
  await page.setViewportSize({ width: 320, height: 844 });
  const { block, errors } = await setup(page, baseURL!, "achilles", "invalid");
  await page.getByRole("button", { name: block.display_name, exact: false }).first().click();
  await expect(page.getByRole("dialog")).toContainText("Demo not assigned");
  await expect(page.getByRole("dialog").locator("iframe, .ex-demo")).toHaveCount(0);
  await expect(page.getByRole("dialog")).toContainText("1 × 10");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});
