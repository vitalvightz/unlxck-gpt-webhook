import { expect, test } from "@playwright/test";
import { isolateFromNetwork } from "./support";

test.beforeEach(async ({ page, baseURL }) => {
  await isolateFromNetwork(page, baseURL ?? "http://127.0.0.1:3100");
  await page.addInitScript(() => {
    // Inspect generated PCM without fetching a blob (connect-src stays strict).
    const blobs = new Map<string, Blob>();
    const createUrl = URL.createObjectURL.bind(URL);
    URL.createObjectURL = (blob) => {
      const url = createUrl(blob);
      if (blob instanceof Blob) blobs.set(url, blob);
      return url;
    };
    Object.assign(window, { __roundTimerAudioBlobs: blobs });
    // Seed once: reload must exercise the saved run, not overwrite it.
    if (localStorage.getItem("round-timer-e2e")) return;
    localStorage.setItem("round-timer-e2e", "true");
    localStorage.setItem("unlxck.session-timer.free-format", JSON.stringify({ rounds: 3, workSec: 5, restSec: 2 }));
    localStorage.setItem("unlxck.session-timer.settings", JSON.stringify({ prepSec: 0, voice: false }));
  });
});

test("round media carries the bells while page JavaScript is paused, then the UI catches up", async ({ page, context }, testInfo) => {
  test.setTimeout(60_000);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const response = await page.goto("/timer");
  expect(response?.headers()["content-security-policy"]).toContain("media-src 'self' blob:");
  await expect(page).toHaveTitle(/UNLXCK/i);
  await page.getByRole("button", { name: "Start round 1", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Round audio playing" })).toBeVisible();
  const media = page.locator("audio[data-round-audio]");
  await expect(media).toHaveCount(1);
  const before = await media.evaluate((audio: HTMLAudioElement) => audio.currentTime);

  // Verify actual rendered PCM contains bell energy at the engine's deadlines.
  const waveform = await media.evaluate(async (audio: HTMLAudioElement) => {
    const blobs = (window as unknown as { __roundTimerAudioBlobs: Map<string, Blob> }).__roundTimerAudioBlobs;
    const pcm = new DataView(await blobs.get(audio.src)!.arrayBuffer());
    const energy = (seconds: number) => {
      let sum = 0;
      for (let i = 0; i < 1600; i += 1) sum += Math.abs(pcm.getInt16(44 + (Math.round(seconds * 16000) + i) * 2, true));
      return sum;
    };
    return { duration: audio.duration, silence: energy(1), endBell: energy(5.05), startBell: energy(7.05), finish: energy(19.05) };
  });
  expect(waveform.duration).toBeCloseTo(23, 1);
  expect(waveform.silence).toBe(0);
  expect(waveform.endBell).toBeGreaterThan(1000);
  expect(waveform.startBell).toBeGreaterThan(1000);
  expect(waveform.finish).toBeGreaterThan(1000);
  await page.screenshot({ path: testInfo.outputPath("round-timer-desktop.png") });

  const cdp = await context.newCDPSession(page);
  await cdp.send("Debugger.enable");
  await cdp.send("Debugger.pause");
  try {
    // Node's timer runs outside the browser. The page cannot trigger any bells.
    await new Promise((resolve) => setTimeout(resolve, 9000));
  } finally {
    await cdp.send("Debugger.resume");
    await cdp.send("Debugger.disable");
  }
  const after = await media.evaluate((audio: HTMLAudioElement) => ({ time: audio.currentTime, paused: audio.paused }));
  expect(after.paused).toBe(false);
  expect(after.time - before).toBeGreaterThan(8);
  await expect(page.locator(".st-clock-caption")).toHaveText("Round 2 / 3");
  await expect(page.locator(".st-done-title")).toHaveText("Session complete", { timeout: 15_000 });
  // The final bell's decay must survive the engine finishing the run.
  await expect(media).toHaveCount(1);
  await expect(media).toHaveCount(0, { timeout: 7000 });
  expect(errors).toEqual([]);
});

test("pause, resume, edits and interrupted playback keep one correctly aligned track", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/timer");
  await page.getByRole("button", { name: "Start round 1", exact: true }).click();
  await expect(page.locator(".st-audio-status")).toContainText("Round audio playing");
  const media = page.locator("audio[data-round-audio]");
  await page.getByRole("button", { name: "Pause timer", exact: true }).click();
  await expect(media).toHaveCount(0);
  const paused = await page.locator(".st-clock-digits").textContent();
  await page.waitForTimeout(1100);
  await expect(page.locator(".st-clock-digits")).toHaveText(paused!);
  await page.getByRole("button", { name: "Resume timer", exact: true }).click();
  await expect(page.locator(".st-audio-status")).toContainText("Round audio playing");
  const duration = await media.evaluate((audio: HTMLAudioElement) => audio.duration);
  await page.getByRole("button", { name: "Add 10 seconds", exact: true }).click();
  await expect(page.locator(".st-audio-status")).toContainText("Round audio playing");
  await expect(media).toHaveCount(1);
  expect(await media.evaluate((audio: HTMLAudioElement) => audio.duration)).toBeGreaterThan(duration + 8);
  await media.evaluate((audio: HTMLAudioElement) => audio.pause());
  await expect(page.locator(".st-audio-status")).toContainText("was interrupted");
  await page.getByRole("button", { name: "Enable round audio", exact: true }).click();
  await expect(page.locator(".st-audio-status")).toContainText("Round audio playing");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("round-timer-mobile.png") });
  await page.getByRole("button", { name: "Minimise timer", exact: true }).click();
  await expect(page.locator(".st-mini")).toBeVisible();
  await expect(media).toHaveCount(1);
  await page.goto("/timer");
  await expect(page.locator(".st-root")).toBeVisible();
  // A reload either restores permitted playback or exposes a gesture to enable it.
  await expect(page.locator(".st-audio-status")).toHaveText(/Round audio playing|Round audio is unavailable/);
});

test("denied media playback exposes the foreground fallback and releases its track", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.addInitScript(() => {
    HTMLMediaElement.prototype.play = () => Promise.reject(new DOMException("Playback denied for test", "NotAllowedError"));
  });
  await page.goto("/timer");
  await page.getByRole("button", { name: "Start round 1", exact: true }).click();
  await expect(page.locator(".st-audio-status")).toContainText("Round audio is unavailable. Keep this screen open.");
  await expect(page.getByRole("button", { name: "Enable round audio", exact: true })).toBeVisible();
  await expect(page.locator("audio[data-round-audio]")).toHaveCount(0);
  await expect(page.locator(".st-clock-digits")).not.toHaveText("0:05");
  expect(errors).toEqual([]);
});
