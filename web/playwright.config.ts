import { defineConfig, devices } from "@playwright/test";

/**
 * Lightweight, deterministic smoke/accessibility config for the web app.
 *
 * - Single Chromium project to keep runtime + CI install cost low.
 * - `webServer` runs the production server (`next start`) against a build that
 *   was produced with CI-safe placeholder public env vars. NEXT_PUBLIC_* values
 *   are inlined at build time, so the build step (local or CI) must set the
 *   placeholder Supabase/API values — see README "Frontend quality gates".
 * - No real Supabase/OpenAI credentials are used; tests additionally block all
 *   cross-origin network traffic so they never depend on external services.
 */
const PORT = Number(process.env.E2E_PORT ?? 3100);
const HOST = "127.0.0.1";
const BASE_URL = `http://${HOST}:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: `npm run start -- --port ${PORT} --hostname ${HOST}`,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
