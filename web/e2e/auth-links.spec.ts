import { expect, test, type Page } from "@playwright/test";

import { isolateFromNetwork } from "./support";

const BASE_URL = "http://127.0.0.1:3100";

// supabase-js persists under `sb-${hostname.split(".")[0]}-auth-token`. This
// must match the NEXT_PUBLIC_SUPABASE_URL the bundle was built with — see the
// build env in .github/workflows/web-build.yml. If it drifts, the
// "verified recovery link opens the form" test below fails, which is the
// signal that session seeding stopped working (and that the refusal tests
// have become vacuous).
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://stub.supabase.co";
const STORAGE_KEY = `sb-${new URL(SUPABASE_URL).hostname.split(".")[0]}-auth-token`;

const EXISTING_TOKEN = "PRE_EXISTING_SESSION_ACCESS_TOKEN";
const EXPIRED_MESSAGE = "This link has expired or has already been used.";
const MISSING_MESSAGE = "This link is missing its verification token.";

function seededSession(accessToken: string): string {
  return JSON.stringify({
    access_token: accessToken,
    token_type: "bearer",
    expires_in: 86_400,
    // Far enough out that supabase-js does not attempt a refresh.
    expires_at: Math.floor(Date.now() / 1000) + 86_400,
    refresh_token: "seeded-refresh-token",
    user: {
      id: "00000000-0000-4000-8000-000000000001",
      aud: "authenticated",
      role: "authenticated",
      email: "athlete@example.com",
      created_at: new Date().toISOString(),
      app_metadata: {},
      user_metadata: {},
    },
  });
}

/** Put a signed-in session in storage before any app code runs. */
async function signIn(page: Page, accessToken = EXISTING_TOKEN): Promise<void> {
  await page.addInitScript(
    ([key, value]) => window.localStorage.setItem(key, value),
    [STORAGE_KEY, seededSession(accessToken)] as const,
  );
}

function passwordFields(page: Page) {
  return page.locator('input[type="password"]');
}

test.describe("password reset requires a verified recovery link", () => {
  // supabase-js deliberately keeps an existing session when it fails to consume
  // a URL ("Don't remove existing session on URL login failure"), so a
  // credential-shaped parameter must never be mistaken for proof that Supabase
  // accepted a recovery link. Otherwise anyone with access to a signed-in
  // browser could set a new password without knowing the current one, which is
  // the check /settings enforces.
  const refusals = [
    { name: "an arbitrary code query parameter", path: "/reset-password?code=arbitrary" },
    { name: "a stale access token fragment", path: "/reset-password#access_token=stale&type=recovery" },
    { name: "a bare type=recovery parameter", path: "/reset-password?type=recovery" },
    { name: "no link parameters at all", path: "/reset-password" },
  ];

  for (const { name, path } of refusals) {
    test(`refuses ${name} for a signed-in athlete`, async ({ page, baseURL }) => {
      await signIn(page);
      await isolateFromNetwork(page, baseURL ?? BASE_URL);
      await page.goto(path, { waitUntil: "domcontentloaded" });

      // The invariant that matters: the form never opens.
      await expect(passwordFields(page)).toHaveCount(0);
      // And the athlete is told why. A PKCE code is judged by Supabase, which
      // is unreachable under network isolation, so allow for the bounded wait
      // the page gives that exchange.
      await expect(page.getByRole("link", { name: "Request a new reset link" })).toBeVisible({
        timeout: 20_000,
      });
      await expect(passwordFields(page)).toHaveCount(0);
    });
  }

  test("opens the form when the stored session is the one the link minted", async ({ page, baseURL }) => {
    // The state supabase-js leaves behind for a genuine recovery link: the
    // session in storage carries exactly the access token from the URL. This
    // also proves the seeding above works — if it silently failed, every
    // refusal test would pass for the wrong reason.
    await signIn(page);
    await isolateFromNetwork(page, baseURL ?? BASE_URL);
    await page.goto(`/reset-password#access_token=${EXISTING_TOKEN}&type=recovery`, {
      waitUntil: "domcontentloaded",
    });

    await expect(passwordFields(page)).toHaveCount(2);
    await expect(page.getByRole("button", { name: "Update password" })).toBeVisible();
  });

  test("sends a signed-in athlete with no recovery link to Settings", async ({ page, baseURL }) => {
    await signIn(page);
    await isolateFromNetwork(page, baseURL ?? BASE_URL);
    await page.goto("/reset-password", { waitUntil: "domcontentloaded" });

    await expect(page.getByText(MISSING_MESSAGE)).toBeVisible();
    await expect(page.getByRole("link", { name: "Change your password in Settings" })).toBeVisible();
  });
});

test.describe("spent auth links explain themselves", () => {
  // Supabase reports rejection on the fragment (implicit flow) and on the query
  // string (PKCE and /auth/v1/verify). Reading only one half left an athlete on
  // a page that looked like their click did nothing.
  const landings = [
    { name: "reset link, fragment error", path: "/reset-password#error=access_denied&error_code=otp_expired" },
    { name: "reset link, query error", path: "/reset-password?error=access_denied&error_code=otp_expired" },
    { name: "sign-in link, fragment error", path: "/login#error=access_denied&error_code=otp_expired" },
    { name: "sign-in link, query error", path: "/login?error=access_denied&error_code=otp_expired" },
  ];

  for (const { name, path } of landings) {
    test(`${name} shows the expired message`, async ({ page, baseURL }) => {
      await isolateFromNetwork(page, baseURL ?? BASE_URL);
      await page.goto(path, { waitUntil: "domcontentloaded" });

      await expect(page.getByText(EXPIRED_MESSAGE)).toBeVisible();
      // Tokens and error codes must not survive in history or a later Referer.
      await expect
        .poll(() => page.url(), { message: "auth params should be scrubbed from the URL" })
        .not.toMatch(/access_token|refresh_token|error_code|[?&#]code=/);
    });
  }

  test("an anonymous visit with no token does not offer a dead form", async ({ page, baseURL }) => {
    await isolateFromNetwork(page, baseURL ?? BASE_URL);
    await page.goto("/reset-password", { waitUntil: "domcontentloaded" });

    await expect(page.getByText(MISSING_MESSAGE)).toBeVisible();
    await expect(passwordFields(page)).toHaveCount(0);
  });

  test("a clean login page shows no auth link error", async ({ page, baseURL }) => {
    await isolateFromNetwork(page, baseURL ?? BASE_URL);
    await page.goto("/login", { waitUntil: "domcontentloaded" });

    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByText(EXPIRED_MESSAGE)).toHaveCount(0);
    await expect(page.getByText(MISSING_MESSAGE)).toHaveCount(0);
  });
});
