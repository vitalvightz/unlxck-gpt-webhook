// Vercel deployment hostnames (`unlxck-abc123-team.vercel.app`) change on every
// push and sit behind deployment protection. A link built from one is dead by
// the time an athlete opens their inbox — they land on Vercel's own branded
// gate, not UNLXCK. Auth emails must always carry the canonical origin.
const VERCEL_HOST_PATTERN = /(^|\.)vercel\.app$/i;

function normalizeOrigin(value: string | null | undefined): string {
  const trimmed = value?.trim();
  if (!trimmed) {
    return "";
  }

  // System env vars like VERCEL_PROJECT_PRODUCTION_URL are bare hostnames.
  const candidate = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;

  try {
    return new URL(candidate).origin;
  } catch {
    return "";
  }
}

/**
 * The canonical public origin of the app.
 *
 * Order matters. `NEXT_PUBLIC_SITE_URL` is the explicit answer; Vercel's
 * project production URL is the stable custom/production domain (never a
 * per-deployment preview host); `window.location.origin` is the last resort so
 * local development still works.
 */
export function getSiteOrigin(): string {
  const configured = normalizeOrigin(process.env.NEXT_PUBLIC_SITE_URL);
  if (configured) {
    return configured;
  }

  const vercelProduction = normalizeOrigin(process.env.NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL);
  if (vercelProduction) {
    return vercelProduction;
  }

  if (typeof window !== "undefined") {
    return normalizeOrigin(window.location.origin);
  }

  return "";
}

export function isVercelDeploymentOrigin(origin: string): boolean {
  const normalized = normalizeOrigin(origin);
  if (!normalized) {
    return false;
  }

  try {
    return VERCEL_HOST_PATTERN.test(new URL(normalized).hostname);
  } catch {
    return false;
  }
}

/**
 * Absolute URL Supabase should send an athlete back to after they follow an
 * auth email link. Returns `undefined` when no origin can be resolved, which
 * makes supabase-js fall back to the project's configured Site URL rather than
 * emailing a relative or malformed link.
 *
 * Every path passed here must also be listed in the Supabase dashboard under
 * Authentication -> URL Configuration -> Redirect URLs. Supabase silently
 * rewrites any non-allow-listed `redirect_to` to the project Site URL, so an
 * unlisted path is indistinguishable from a misconfigured origin.
 */
export function buildAuthRedirectUrl(path: string): string | undefined {
  const origin = getSiteOrigin();
  if (!origin) {
    return undefined;
  }

  if (process.env.NODE_ENV !== "production" && isVercelDeploymentOrigin(origin)) {
    console.warn(
      `[unlxck] Auth emails will link to ${origin}. Set NEXT_PUBLIC_SITE_URL to the production domain — ` +
        "*.vercel.app hosts are deployment-protected and show a Vercel error page instead of UNLXCK.",
    );
  }

  return `${origin}${path.startsWith("/") ? path : `/${path}`}`;
}
