import type { NextConfig } from "next";
import { withSentryConfig } from "@sentry/nextjs";

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

// Content-Security-Policy is set per-request in proxy.ts so each response
// carries a fresh nonce (script-src uses 'nonce-...' 'strict-dynamic' instead
// of 'unsafe-inline'). The remaining security headers are static and live here.
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
