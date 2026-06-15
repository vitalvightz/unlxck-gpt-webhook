import path from "node:path";
import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs";

// The Next app lives in `web/` but imports the shared Stage 2 policy from
// `../shared/stage2-policy.json` (the single source of truth shared with the
// Python backend). Turbopack otherwise infers the workspace root as `web/` and
// refuses to resolve modules above it; pinning the root to the repo root lets
// that cross-package import resolve. `next build` runs with the cwd set to
// `web/` (CI working-directory and the Vercel project root), so the parent dir
// is the repo root.
const WORKSPACE_ROOT = path.resolve(process.cwd(), "..");

const LOCAL_API_BASE_URL = "http://127.0.0.1:8000";
const MISSING_PRODUCTION_REWRITE_ERROR =
  "NEXT_PUBLIC_API_BASE_URL must be set for production builds so /api rewrites are always configured.";

function resolveBackendUrl(): string | null {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim().replace(/\/$/, "");
  if (configured) {
    return configured;
  }

  if (process.env.NODE_ENV !== "production") {
    return LOCAL_API_BASE_URL;
  }

  return null;
}

// Content-Security-Policy is set per request in proxy.ts so each response can
// carry a fresh nonce for Next's inline bootstrap and hydration scripts.
const SECURITY_HEADERS = [
  // Force HTTPS for a year, including subdomains. `preload` is intentionally
  // omitted until every subdomain is confirmed HTTPS-only — add it only when
  // ready to submit to the HSTS preload list (the decision is hard to reverse).
  {
    key: "Strict-Transport-Security",
    value: "max-age=31536000; includeSubDomains",
  },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=()",
  },
];

const nextConfig: NextConfig = {
  turbopack: {
    root: WORKSPACE_ROOT,
  },
  async rewrites() {
    const backendUrl = resolveBackendUrl();
    if (!backendUrl) {
      throw new Error(MISSING_PRODUCTION_REWRITE_ERROR);
    }

    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: SECURITY_HEADERS,
      },
    ];
  },
};

export default withSentryConfig(nextConfig, {
  org: process.env.SENTRY_ORG ?? "unlxck",
  project: process.env.SENTRY_PROJECT ?? "javascript-nextjs",
  authToken: process.env.SENTRY_AUTH_TOKEN,
  widenClientFileUpload: true,
  silent: !process.env.CI,
});
