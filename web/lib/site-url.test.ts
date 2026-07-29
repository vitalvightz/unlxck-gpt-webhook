import assert from "node:assert/strict";
import test, { afterEach } from "node:test";

import {
  buildAuthRedirectUrl,
  getSiteOrigin,
  isLocalDevelopmentOrigin,
  isVercelDeploymentOrigin,
} from "./site-url.ts";

const ENV_KEYS = ["NEXT_PUBLIC_SITE_URL", "NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL"] as const;

type MutableGlobal = { window?: { location: { origin: string } } };

function setBrowserOrigin(origin: string) {
  (globalThis as MutableGlobal).window = { location: { origin } };
}

afterEach(() => {
  for (const key of ENV_KEYS) {
    delete process.env[key];
  }
  delete (globalThis as MutableGlobal).window;
});

test("prefers the explicitly configured site URL", () => {
  process.env.NEXT_PUBLIC_SITE_URL = "https://app.unlxck.com/";
  process.env.NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL = "unlxck.vercel.app";
  assert.equal(getSiteOrigin(), "https://app.unlxck.com");
  assert.equal(buildAuthRedirectUrl("/reset-password"), "https://app.unlxck.com/reset-password");
});

test("strips paths and trailing slashes down to a bare origin", () => {
  process.env.NEXT_PUBLIC_SITE_URL = "https://app.unlxck.com/login/";
  assert.equal(getSiteOrigin(), "https://app.unlxck.com");
});

test("builds auth redirect URLs with or without a leading slash", () => {
  process.env.NEXT_PUBLIC_SITE_URL = "https://app.unlxck.com";
  assert.equal(buildAuthRedirectUrl("/reset-password"), "https://app.unlxck.com/reset-password");
  assert.equal(buildAuthRedirectUrl("login"), "https://app.unlxck.com/login");
});

// --- The production bug: a preview deployment must never reach an inbox. ---

test("refuses to email a Vercel preview host when NEXT_PUBLIC_SITE_URL is missing", () => {
  setBrowserOrigin("https://unlxck-git-fix-auth-team.vercel.app");
  assert.equal(
    buildAuthRedirectUrl("/reset-password"),
    undefined,
    "supabase-js must fall back to the project Site URL rather than email a protected preview host",
  );
});

test("refuses a per-deployment Vercel host even though the page loads fine on it", () => {
  setBrowserOrigin("https://unlxck-a1b2c3d4e5-vitalvightz.vercel.app");
  assert.equal(buildAuthRedirectUrl("/login"), undefined);
});

test("refuses any deployed non-local origin that was only auto-detected", () => {
  setBrowserOrigin("https://staging.unlxck.com");
  assert.equal(buildAuthRedirectUrl("/login"), undefined);
});

test("still honours a Vercel host when an operator configured it explicitly", () => {
  // unlxck.vercel.app is the stable production alias and is not deployment
  // protected, so an explicit choice to use it must keep working.
  process.env.NEXT_PUBLIC_SITE_URL = "https://unlxck.vercel.app";
  setBrowserOrigin("https://unlxck-git-fix-team.vercel.app");
  assert.equal(buildAuthRedirectUrl("/login"), "https://unlxck.vercel.app/login");
});

test("ignores a Vercel host arriving via the system production URL variable", () => {
  // NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL is only exposed when the project
  // enables system environment variables, so it is a bonus, never the plan —
  // and a *.vercel.app value from it is not an operator decision.
  process.env.NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL = "unlxck.vercel.app";
  setBrowserOrigin("https://unlxck-git-fix-team.vercel.app");
  assert.equal(buildAuthRedirectUrl("/login"), undefined);
});

test("uses the system production URL variable when it is a custom domain", () => {
  process.env.NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL = "app.unlxck.com";
  setBrowserOrigin("https://unlxck-git-fix-team.vercel.app");
  assert.equal(buildAuthRedirectUrl("/login"), "https://app.unlxck.com/login");
});

test("allows the browser origin for local development", () => {
  setBrowserOrigin("http://localhost:3000");
  assert.equal(buildAuthRedirectUrl("/reset-password"), "http://localhost:3000/reset-password");

  setBrowserOrigin("http://127.0.0.1:3000");
  assert.equal(buildAuthRedirectUrl("/login"), "http://127.0.0.1:3000/login");
});

test("returns undefined on the server with nothing configured", () => {
  assert.equal(buildAuthRedirectUrl("/reset-password"), undefined);
});

// --- Scheme handling: never fabricate a host out of a non-http value. ---

test("rejects non-http schemes instead of prefixing https:// onto them", () => {
  // "https://" + "ftp://app.unlxck.com" parses as the host "ftp".
  for (const value of [
    "ftp://app.unlxck.com",
    "javascript:alert(1)",
    "mailto:ops@unlxck.com",
    "data:text/html,hello",
    "file:///etc/passwd",
    "//evil.example.com",
  ]) {
    process.env.NEXT_PUBLIC_SITE_URL = value;
    assert.equal(getSiteOrigin(), "", `expected ${value} to be rejected`);
    assert.equal(buildAuthRedirectUrl("/login"), undefined, `expected ${value} to be rejected`);
  }
});

test("accepts bare hostnames, including a host:port that is not a scheme", () => {
  process.env.NEXT_PUBLIC_SITE_URL = "app.unlxck.com";
  assert.equal(getSiteOrigin(), "https://app.unlxck.com");

  process.env.NEXT_PUBLIC_SITE_URL = "localhost:3000";
  assert.equal(getSiteOrigin(), "https://localhost:3000");

  process.env.NEXT_PUBLIC_SITE_URL = "127.0.0.1:3000";
  assert.equal(getSiteOrigin(), "https://127.0.0.1:3000");
});

test("accepts http and uppercase schemes", () => {
  process.env.NEXT_PUBLIC_SITE_URL = "http://localhost:3000";
  assert.equal(getSiteOrigin(), "http://localhost:3000");

  process.env.NEXT_PUBLIC_SITE_URL = "HTTPS://APP.UNLXCK.COM";
  assert.equal(getSiteOrigin(), "https://app.unlxck.com");
});

test("ignores blank and malformed configuration", () => {
  for (const value of ["   ", "https://", "http://", ":::"]) {
    process.env.NEXT_PUBLIC_SITE_URL = value;
    assert.equal(getSiteOrigin(), "", `expected ${JSON.stringify(value)} to be rejected`);
  }
});

// --- Host classification ---

test("recognizes Vercel deployment hosts", () => {
  assert.equal(isVercelDeploymentOrigin("https://unlxck-git-main-team.vercel.app"), true);
  assert.equal(isVercelDeploymentOrigin("unlxck.vercel.app"), true);
  assert.equal(isVercelDeploymentOrigin("https://app.unlxck.com"), false);
  // A lookalike suffix must not be treated as a Vercel host.
  assert.equal(isVercelDeploymentOrigin("https://notvercel.app"), false);
  assert.equal(isVercelDeploymentOrigin(""), false);
});

test("recognizes local development hosts", () => {
  assert.equal(isLocalDevelopmentOrigin("http://localhost:3000"), true);
  assert.equal(isLocalDevelopmentOrigin("http://127.0.0.1:3000"), true);
  assert.equal(isLocalDevelopmentOrigin("http://[::1]:3000"), true);
  assert.equal(isLocalDevelopmentOrigin("http://unlxck.localhost:3000"), true);
  assert.equal(isLocalDevelopmentOrigin("https://app.unlxck.com"), false);
  assert.equal(isLocalDevelopmentOrigin("https://unlxck.vercel.app"), false);
  // Not local just because the name says so.
  assert.equal(isLocalDevelopmentOrigin("https://localhost.evil.example.com"), false);
});
