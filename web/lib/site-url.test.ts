import assert from "node:assert/strict";
import test, { afterEach } from "node:test";

import { buildAuthRedirectUrl, getSiteOrigin, isVercelDeploymentOrigin } from "./site-url.ts";

const ENV_KEYS = ["NEXT_PUBLIC_SITE_URL", "NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL"] as const;

afterEach(() => {
  for (const key of ENV_KEYS) {
    delete process.env[key];
  }
});

test("prefers the explicitly configured site URL", () => {
  process.env.NEXT_PUBLIC_SITE_URL = "https://app.unlxck.com/";
  process.env.NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL = "unlxck.vercel.app";
  assert.equal(getSiteOrigin(), "https://app.unlxck.com");
});

test("strips paths and trailing slashes down to a bare origin", () => {
  process.env.NEXT_PUBLIC_SITE_URL = "https://app.unlxck.com/login/";
  assert.equal(getSiteOrigin(), "https://app.unlxck.com");
});

test("falls back to the Vercel production domain rather than the current deployment host", () => {
  process.env.NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL = "app.unlxck.com";
  assert.equal(getSiteOrigin(), "https://app.unlxck.com");
});

test("ignores blank and malformed configuration", () => {
  process.env.NEXT_PUBLIC_SITE_URL = "   ";
  process.env.NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL = "https://";
  assert.equal(getSiteOrigin(), "");
});

test("builds auth redirect URLs on the canonical origin", () => {
  process.env.NEXT_PUBLIC_SITE_URL = "https://app.unlxck.com";
  assert.equal(buildAuthRedirectUrl("/reset-password"), "https://app.unlxck.com/reset-password");
  assert.equal(buildAuthRedirectUrl("login"), "https://app.unlxck.com/login");
});

test("returns undefined when no origin is resolvable so supabase-js uses the project Site URL", () => {
  assert.equal(buildAuthRedirectUrl("/reset-password"), undefined);
});

test("recognizes Vercel deployment hosts", () => {
  assert.equal(isVercelDeploymentOrigin("https://unlxck-git-main-team.vercel.app"), true);
  assert.equal(isVercelDeploymentOrigin("unlxck.vercel.app"), true);
  assert.equal(isVercelDeploymentOrigin("https://app.unlxck.com"), false);
  // Not a subdomain of vercel.app — a lookalike must not be treated as one.
  assert.equal(isVercelDeploymentOrigin("https://notvercel.app"), false);
  assert.equal(isVercelDeploymentOrigin(""), false);
});
