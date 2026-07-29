// Vercel deployment hostnames (`unlxck-abc123-team.vercel.app`) change on every
// push and preview deployments sit behind deployment protection. A link built
// from one is dead by the time an athlete opens their inbox — they land on
// Vercel's own branded gate, not UNLXCK. Auth emails must never carry one
// unless an operator explicitly configured it.
const VERCEL_HOST_PATTERN = /(^|\.)vercel\.app$/i;

// Hosts where falling back to the browser's own origin is safe, because there
// is no deployment indirection to get wrong.
const LOCAL_HOSTNAMES = new Set(["localhost", "127.0.0.1", "[::1]", "0.0.0.0"]);

/**
 * Parse a configured value into a bare `https://host[:port]` origin, or "" if
 * it cannot be trusted.
 *
 * Blindly prefixing "https://" onto anything without a leading `http` is what
 * turns `ftp://app.unlxck.com` into `https://ftp` and `mailto:ops@unlxck.com`
 * into `https://unlxck.com` — silently wrong hosts in an emailed link. A scheme
 * that is present must be http or https; only genuine bare hostnames get a
 * scheme added.
 */
function parseOrigin(value: string | null | undefined): string {
  const trimmed = value?.trim();
  if (!trimmed) {
    return "";
  }

  let candidate: string;
  const schemeSeparator = trimmed.indexOf("://");

  if (schemeSeparator !== -1) {
    const scheme = trimmed.slice(0, schemeSeparator).toLowerCase();
    if (scheme !== "http" && scheme !== "https") {
      return "";
    }
    candidate = trimmed;
  } else if (trimmed.startsWith("//")) {
    // Protocol-relative. Not a bare hostname — refuse to guess a scheme.
    return "";
  } else if (/^[a-z][a-z0-9+.-]*:(?!\d)/i.test(trimmed)) {
    // Opaque scheme such as javascript:, mailto: or data:. A colon followed by
    // digits is a port on a bare host ("localhost:3000"), which stays allowed.
    return "";
  } else {
    candidate = `https://${trimmed}`;
  }

  try {
    const url = new URL(candidate);
    if ((url.protocol !== "http:" && url.protocol !== "https:") || !url.hostname) {
      return "";
    }
    return url.origin;
  } catch {
    return "";
  }
}

export function isVercelDeploymentOrigin(origin: string): boolean {
  const normalized = parseOrigin(origin);
  if (!normalized) {
    return false;
  }
  return VERCEL_HOST_PATTERN.test(new URL(normalized).hostname);
}

export function isLocalDevelopmentOrigin(origin: string): boolean {
  const normalized = parseOrigin(origin);
  if (!normalized) {
    return false;
  }
  const { hostname } = new URL(normalized);
  return LOCAL_HOSTNAMES.has(hostname) || hostname.endsWith(".localhost");
}

/**
 * The app's public origin, for general use. Callers that put the result into an
 * email must use `buildAuthRedirectUrl` instead — this one still falls back to
 * whatever host the browser happens to be on.
 */
export function getSiteOrigin(): string {
  const configured = parseOrigin(process.env.NEXT_PUBLIC_SITE_URL);
  if (configured) {
    return configured;
  }

  const vercelProduction = parseOrigin(process.env.NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL);
  if (vercelProduction) {
    return vercelProduction;
  }

  if (typeof window !== "undefined") {
    return parseOrigin(window.location.origin);
  }

  return "";
}

/**
 * The origin an auth email may link back to.
 *
 * Deliberately stricter than `getSiteOrigin()`. An emailed link is opened
 * minutes or hours later, from a different device, so an origin that merely
 * works right now in this tab is not good enough:
 *
 * 1. `NEXT_PUBLIC_SITE_URL` — an explicit operator decision, always honoured.
 * 2. `NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL` — only useful when the project
 *    has a custom domain, and only present when "Automatically expose System
 *    Environment Variables" is enabled, so it is a bonus and never the plan. A
 *    `*.vercel.app` value here is rejected.
 * 3. `window.location.origin` — local development only.
 *
 * Anything else yields `undefined`, which makes supabase-js fall back to the
 * project's Site URL. Landing on production is always better than landing on a
 * protected preview host, so refusing to answer is the safe failure.
 */
function resolveAuthEmailOrigin(): string {
  const configured = parseOrigin(process.env.NEXT_PUBLIC_SITE_URL);
  if (configured) {
    return configured;
  }

  const vercelProduction = parseOrigin(process.env.NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL);
  if (vercelProduction && !isVercelDeploymentOrigin(vercelProduction)) {
    return vercelProduction;
  }

  const currentOrigin = typeof window !== "undefined" ? parseOrigin(window.location.origin) : "";
  if (currentOrigin && isLocalDevelopmentOrigin(currentOrigin)) {
    return currentOrigin;
  }

  return "";
}

/**
 * Absolute URL Supabase should send an athlete back to after they follow an
 * auth email link, or `undefined` when no origin can be trusted.
 *
 * Every path passed here must also be listed in the Supabase dashboard under
 * Authentication -> URL Configuration -> Redirect URLs. Supabase silently
 * rewrites any non-allow-listed `redirect_to` to the project Site URL, so an
 * unlisted path is indistinguishable from a misconfigured origin.
 */
export function buildAuthRedirectUrl(path: string): string | undefined {
  const origin = resolveAuthEmailOrigin();

  if (!origin) {
    console.warn(
      "[unlxck] No trusted origin for auth emails; Supabase will use the project Site URL. " +
        "Set NEXT_PUBLIC_SITE_URL to the production domain in every Vercel environment " +
        "(Production, Preview and Development).",
    );
    return undefined;
  }

  return `${origin}${path.startsWith("/") ? path : `/${path}`}`;
}
