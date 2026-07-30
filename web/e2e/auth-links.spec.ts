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

const USER_ID = "00000000-0000-4000-8000-000000000001";
const OTHER_USER_ID = "00000000-0000-4000-8000-000000000002";
// Mirrors web/lib/password-recovery.ts.
const RECOVERY_KEY = "unlxck.password-recovery";
const RECOVERY_TTL_MS = 15 * 60 * 1000;

function seededUser(id = USER_ID) {
  return {
    id,
    aud: "authenticated",
    role: "authenticated",
    email: "athlete@example.com",
    created_at: new Date().toISOString(),
    app_metadata: {},
    user_metadata: {},
  };
}

function seededSession(accessToken: string): string {
  return JSON.stringify({
    access_token: accessToken,
    token_type: "bearer",
    expires_in: 86_400,
    // Far enough out that supabase-js does not attempt a refresh.
    expires_at: Math.floor(Date.now() / 1000) + 86_400,
    refresh_token: "seeded-refresh-token",
    user: seededUser(),
  });
}

/** Put a signed-in session in storage before any app code runs. */
async function signIn(page: Page, accessToken = EXISTING_TOKEN): Promise<void> {
  await page.addInitScript(
    ([key, value]) => window.localStorage.setItem(key, value),
    [STORAGE_KEY, seededSession(accessToken)] as const,
  );
}

/**
 * Plant a recovery marker directly. Only for the negative cases — the happy
 * path deliberately lets the app write its own via a real PASSWORD_RECOVERY
 * event, so the tests never assume the wiring they are meant to prove.
 *
 * Seeds once per context. `addInitScript` re-runs on every navigation, so
 * without the sentinel a test that navigates twice would silently re-plant the
 * marker and could never observe one being spent.
 */
async function seedRecoveryMarker(page: Page, userId: string, ageMs = 0): Promise<void> {
  await page.addInitScript(
    ([key, value, sentinel]) => {
      if (window.localStorage.getItem(sentinel)) {
        return;
      }
      window.localStorage.setItem(sentinel, "1");
      window.sessionStorage.setItem(key, value);
    },
    [RECOVERY_KEY, JSON.stringify({ userId, at: Date.now() - ageMs }), "e2e.recovery-seeded"] as const,
  );
}

/**
 * Network isolation that additionally answers the two Supabase auth endpoints a
 * real recovery callback needs.
 *
 * - `GET /auth/v1/user`: supabase-js calls it from `_getSessionFromURL` to build
 *   the session behind an implicit-grant callback. Answering it is what lets a
 *   recovery fragment be consumed for real, so `PASSWORD_RECOVERY` is genuinely
 *   emitted rather than simulated.
 * - `POST /auth/v1/token`: the app's `/api/*` calls are stubbed 401 here, which
 *   sends AuthProvider down its refresh path. Left aborted, auth-js retries that
 *   refresh with backoff **while holding its auth lock**, and every other
 *   `getSession()` in the app queues behind it for longer than the test timeout.
 *   Answering it keeps the lock moving. The refreshed session deliberately keeps
 *   the same user id, so this also proves the recovery marker survives a token
 *   refresh.
 *
 * Registered after `isolateFromNetwork` because Playwright gives the most
 * recently added handler priority.
 */
async function isolateWithSupabaseUser(page: Page, baseURL: string, id = USER_ID): Promise<void> {
  await isolateFromNetwork(page, baseURL);

  await page.route("**/auth/v1/user**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(seededUser(id)),
    });
  });

  await page.route("**/auth/v1/token**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        access_token: "REFRESHED_ACCESS_TOKEN",
        token_type: "bearer",
        expires_in: 3_600,
        expires_at: Math.floor(Date.now() / 1000) + 3_600,
        refresh_token: "REFRESHED_REFRESH_TOKEN",
        user: seededUser(id),
      }),
    });
  });
}

function recoveryFragment(accessToken: string): string {
  return `#access_token=${accessToken}&refresh_token=seeded-refresh-token&expires_in=3600&token_type=bearer&type=recovery`;
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
    await expect(page.getByRole("link", { name: "Change it in Settings" })).toBeVisible();
  });
});

test.describe("a recovery session reaches the reset form wherever it lands", () => {
  // Supabase picks the landing route: any redirect_to that is not on its allow
  // list is rewritten to the project Site URL. That is what shipped to
  // production — the link consumed its tokens on the homepage, the athlete was
  // simply signed in, and the reset never happened.
  //
  // These are the routes Supabase can actually deliver to: the Site URL and the
  // allow-listed public ones. A protected route is deliberately not covered —
  // it can be neither a Site URL nor a sensible Redirect URL, and its own guard
  // bounces an unhydrated session to /login, so a test there races app
  // behaviour unrelated to recovery.
  for (const landing of ["/", "/login", "/forgot-password"]) {
    test(`carries a recovery landing on ${landing} to the reset form`, async ({ page, baseURL }) => {
      await isolateWithSupabaseUser(page, baseURL ?? BASE_URL);
      await page.goto(`${landing}${recoveryFragment("RECOVERY_MINTED_TOKEN")}`, {
        waitUntil: "domcontentloaded",
      });

      await expect(page).toHaveURL(/\/reset-password$/);
      await expect(passwordFields(page)).toHaveCount(2);
      await expect(page.getByRole("button", { name: "Update password" })).toBeVisible();
    });
  }

  test("completes even when sessionStorage is blocked", async ({ page, baseURL }) => {
    // The redirect fires as soon as Supabase verifies the link, so if a blocked
    // write meant no proof, the athlete would land on a form that refuses them
    // for "missing" verification. Email clients open links in exactly the kind
    // of restrictive in-app browser where this bites.
    await page.addInitScript(() => {
      Object.defineProperty(window, "sessionStorage", {
        configurable: true,
        get() {
          throw new DOMException("storage blocked by policy", "SecurityError");
        },
      });
    });
    await isolateWithSupabaseUser(page, baseURL ?? BASE_URL);
    await page.goto(`/${recoveryFragment("RECOVERY_MINTED_TOKEN")}`, { waitUntil: "domcontentloaded" });

    await expect(page).toHaveURL(/\/reset-password$/);
    await expect(passwordFields(page)).toHaveCount(2);
  });

  test("a rejected link spends an earlier recovery marker", async ({ page, baseURL }) => {
    // Opening a stale link after a good one must not leave the marker live —
    // otherwise simply revisiting /reset-password inside the TTL reopens the
    // form on an ordinary session.
    await signIn(page);
    await seedRecoveryMarker(page, USER_ID);
    await isolateFromNetwork(page, baseURL ?? BASE_URL);

    await page.goto("/reset-password#error=access_denied&error_code=otp_expired", {
      waitUntil: "domcontentloaded",
    });
    await expect(page.getByText(EXPIRED_MESSAGE)).toBeVisible();
    await expect(passwordFields(page)).toHaveCount(0);

    // Same tab, same session, marker still inside its TTL had it survived.
    await page.goto("/reset-password", { waitUntil: "domcontentloaded" });
    await expect(page.getByText(MISSING_MESSAGE)).toBeVisible();
    await expect(passwordFields(page)).toHaveCount(0);
  });

  test("does not leave the marker usable once the recovery is refused", async ({ page, baseURL }) => {
    // A marker aged past its TTL is dead, so the form must stay closed.
    await signIn(page);
    await seedRecoveryMarker(page, USER_ID, RECOVERY_TTL_MS + 60_000);
    await isolateFromNetwork(page, baseURL ?? BASE_URL);
    await page.goto("/reset-password", { waitUntil: "domcontentloaded" });

    await expect(page.getByText(MISSING_MESSAGE)).toBeVisible();
    await expect(passwordFields(page)).toHaveCount(0);
  });

  test("refuses a marker belonging to a different athlete", async ({ page, baseURL }) => {
    // One athlete's recovery must never open the form against another's
    // session, even inside the same tab.
    await signIn(page);
    await seedRecoveryMarker(page, OTHER_USER_ID);
    await isolateFromNetwork(page, baseURL ?? BASE_URL);
    await page.goto("/reset-password", { waitUntil: "domcontentloaded" });

    await expect(page.getByText(MISSING_MESSAGE)).toBeVisible();
    await expect(passwordFields(page)).toHaveCount(0);
  });

  test("leads with a new reset link rather than Settings", async ({ page, baseURL }) => {
    // /settings asks for the current password, which is exactly what an athlete
    // in this flow does not have.
    await signIn(page);
    await isolateFromNetwork(page, baseURL ?? BASE_URL);
    await page.goto("/reset-password", { waitUntil: "domcontentloaded" });

    const primary = page.getByRole("link", { name: "Request a new reset link" });
    await expect(primary).toBeVisible();
    await expect(primary).toHaveClass(/(^|\s)cta(\s|$)/);
    await expect(page.getByRole("link", { name: "Change it in Settings" })).toBeVisible();
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
