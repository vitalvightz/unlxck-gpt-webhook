import { expect, test, type Page, type Route } from "@playwright/test";

import { isolateFromNetwork } from "./support";

const BASE_URL = "http://127.0.0.1:3100";
const SUPABASE_ORIGIN = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "https://stub.supabase.co";
const EMAIL = "new-fighter@example.com";

const user = {
  id: "00000000-0000-4000-8000-0000000000aa",
  aud: "authenticated",
  role: "authenticated",
  email: EMAIL,
  app_metadata: { provider: "email" },
  user_metadata: {},
  identities: [{ id: "identity-1", provider: "email" }],
  created_at: "2026-10-13T00:00:00Z",
  updated_at: "2026-10-13T00:00:00Z",
};

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

/**
 * Signup with email confirmation on: Supabase returns the user without a
 * session, so the form must switch to the one-time-code step instead of
 * sending the athlete off to their inbox and back to the login page.
 */
async function startSignup(page: Page, baseURL: string, verifyStatus: "ok" | "rejected") {
  await isolateFromNetwork(page, baseURL);
  const signupBodies: Array<Record<string, unknown>> = [];
  const complianceBodies: Array<Record<string, unknown>> = [];

  await page.route(`${SUPABASE_ORIGIN}/auth/v1/signup**`, async (route) => {
    signupBodies.push(route.request().postDataJSON());
    await json(route, { ...user, email_confirmed_at: null, confirmation_sent_at: "2026-10-13T00:00:00Z" });
  });
  await page.route(`${SUPABASE_ORIGIN}/auth/v1/verify**`, async (route) => {
    if (verifyStatus === "rejected") {
      await json(route, { code: 403, error_code: "otp_expired", msg: "Token has expired or is invalid" }, 403);
      return;
    }
    await json(route, {
      access_token: "new-athlete-token",
      refresh_token: "new-refresh",
      token_type: "bearer",
      expires_in: 3600,
      expires_at: Math.floor(Date.now() / 1000) + 3600,
      user: { ...user, email_confirmed_at: "2026-10-13T00:01:00Z" },
    });
  });
  await page.route("**/api/me/compliance", async (route) => {
    complianceBodies.push(route.request().postDataJSON());
    await json(route, {});
  });

  await page.goto("/signup", { waitUntil: "domcontentloaded" });
  // Full name is no longer asked at signup; intake collects it.
  await expect(page.getByLabel("Full name")).toHaveCount(0);

  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password", { exact: true }).fill("Southpaw-Jab-Cross-2026");
  await page.getByLabel("Date of birth").fill("1996-05-04");
  await page.locator("#acceptTerms").check();
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page.getByRole("heading", { name: "Check your email" })).toBeVisible();
  await expect(page.getByText(`Enter the code we sent to ${EMAIL}`)).toBeVisible();
  return { signupBodies, complianceBodies };
}

test("a confirmation code finishes signup on the same page", async ({ page, baseURL }) => {
  const { signupBodies, complianceBodies } = await startSignup(page, baseURL ?? BASE_URL, "ok");

  expect(signupBodies).toHaveLength(1);
  expect((signupBodies[0].data as Record<string, unknown>).full_name).toBeUndefined();

  const verify = page.getByRole("button", { name: "Verify and continue" });
  await expect(verify).toBeDisabled();
  await page.getByLabel("Verification code").fill("12 34 56");
  await expect(page.getByLabel("Verification code")).toHaveValue("123456");
  // The first-plan route may hand off again (its guards run against stubbed
  // APIs here), so record every navigation rather than racing the final URL.
  const visited: string[] = [];
  page.on("framenavigated", (frame) => {
    if (frame === page.mainFrame()) visited.push(new URL(frame.url()).pathname);
  });
  await verify.click();

  await expect.poll(() => visited).toContain("/quick-build");
  expect(complianceBodies).toEqual([{ date_of_birth: "1996-05-04", accept_terms: true }]);
});

test("a rejected code explains itself and keeps the athlete on the code step", async ({ page, baseURL }) => {
  await startSignup(page, baseURL ?? BASE_URL, "rejected");

  await page.getByLabel("Verification code").fill("000000");
  await page.getByRole("button", { name: "Verify and continue" }).click();

  await expect(page.locator(".error-banner")).toContainText("That code is wrong or has expired");
  await expect(page).toHaveURL(/\/signup$/);
  await expect(page.getByRole("button", { name: /Resend code in \d+s/ })).toBeDisabled();

  await page.getByRole("button", { name: "Use a different email" }).click();
  await expect(page.getByLabel("Email")).toHaveValue(EMAIL);
});
