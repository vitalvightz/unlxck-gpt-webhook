import { NextRequest, NextResponse } from "next/server";

// Content-Security-Policy is set here (rather than statically in next.config)
// so each request gets a fresh nonce. The script-src uses 'nonce-<value>' plus
// 'strict-dynamic' instead of 'unsafe-inline', so an injected inline <script>
// without the nonce will not execute. Next.js reads the nonce from the request
// Content-Security-Policy header and applies it to its own bootstrap/hydration
// scripts automatically.
//
// Notes / deliberate trade-offs:
// - style-src intentionally keeps 'unsafe-inline'. Nonce-based styles break
//   Google Fonts and Next/CSS-in-JS injected <style> tags, and style injection
//   is a far lower risk than script injection. Tightening this is a separate
//   follow-up.
// - 'unsafe-eval' is kept in development only (required by the dev-mode HMR
//   runtime); production CSP never includes it.
// - The static security headers (HSTS, X-Frame-Options, etc.) remain in
//   next.config.ts; only the CSP moved here.
// - A per-request nonce opts pages out of full static caching. The app is
//   auth-gated and dynamically rendered already, so this is acceptable.
function buildContentSecurityPolicy(nonce: string): string {
  const isDev = process.env.NODE_ENV === "development";
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
  return [
    "default-src 'self'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
    "object-src 'none'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "img-src 'self' data: blob: https:",
    "font-src 'self' data: https://fonts.gstatic.com",
    `connect-src 'self' https://*.supabase.co https://*.sentry.io https://*.ingest.sentry.io ${supabaseUrl}`,
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    "form-action 'self'",
    "upgrade-insecure-requests",
  ].join("; ");
}

export function proxy(request: NextRequest): NextResponse {
  // crypto.randomUUID + btoa are both available in the edge runtime, so no
  // Node Buffer dependency is needed here.
  const nonce = btoa(crypto.randomUUID());
  const csp = buildContentSecurityPolicy(nonce);

  // Forward the nonce and CSP on the request so Next.js can read the nonce and
  // attach it to the scripts it renders.
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  // Run on document requests only. Skip Next internals, static assets, image
  // optimisation, the favicon and prefetch requests so the CSP/nonce is applied
  // to rendered HTML rather than cached static files.
  matcher: [
    {
      source:
        "/((?!api|_next/static|_next/image|favicon.ico|icon.svg|manifest.webmanifest).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
