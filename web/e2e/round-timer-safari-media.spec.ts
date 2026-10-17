import { expect, test } from "@playwright/test";
import { isolateFromNetwork } from "./support";

test("Safari native media Play resumes the real round after a paused placeholder", async ({ page, baseURL }) => {
  await isolateFromNetwork(page, baseURL ?? "http://127.0.0.1:3100");
  await page.addInitScript(() => {
    localStorage.setItem("unlxck.session-timer.free-format", JSON.stringify({ rounds: 3, workSec: 30, restSec: 10 }));
    localStorage.setItem("unlxck.session-timer.settings", JSON.stringify({ prepSec: 0, voice: false }));
  });
  await page.goto("/timer");
  await page.getByRole("button", { name: "Start round 1", exact: true }).click();
  await expect(page.locator(".st-audio-status")).toContainText("Round audio playing");
  const media = page.locator("audio[data-round-audio]");
  await media.evaluate((audio: HTMLAudioElement) => audio.pause());
  await expect(page.getByRole("button", { name: "Resume timer", exact: true })).toBeVisible();
  const clock = await page.locator(".st-clock-digits").textContent();
  await page.waitForTimeout(1100);
  await expect(page.locator(".st-clock-digits")).toHaveText(clock!);
  await expect(media).toHaveJSProperty("paused", true);
  await expect.poll(() => media.evaluate((audio: HTMLAudioElement) => audio.duration)).toBeCloseTo(60, 0);
  await media.evaluate((audio: HTMLAudioElement) => { void audio.play().catch(() => undefined); });
  await expect(page.getByRole("button", { name: "Pause timer", exact: true })).toBeVisible();
  await expect(page.locator(".st-audio-status")).toContainText("Round audio playing");
  await page.getByRole("button", { name: "Pause timer", exact: true }).click();
  await expect(page.getByRole("button", { name: "Resume timer", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Resume timer", exact: true }).click();
  await expect(page.locator(".st-audio-status")).toContainText("Round audio playing");
});
