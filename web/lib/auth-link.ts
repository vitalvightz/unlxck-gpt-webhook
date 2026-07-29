// Supabase hands the outcome of an email link back on the landing URL. Which
// half of the URL carries it depends on the flow: the implicit flow uses the
// fragment (`#access_token=...` / `#error=...`), the PKCE flow and the newer
// `/auth/v1/verify` redirects use the query string (`?code=...` / `?error=...`).
// Reading only one half means a whole class of failures lands on a page that
// looks like nothing happened, which is why an expired link used to leave an
// athlete staring at a blank login form.

export const AUTH_LINK_FEEDBACK = {
  expired: "This link has expired or has already been used. Request a new one.",
  invalid: "This link is not valid. Request a new one.",
  missing: "This link is missing its verification token. Request a new one.",
} as const;

// Codes Supabase uses when the one-time token is simply no longer usable —
// expired, already redeemed, or mangled by an email scanner that pre-fetched it.
const SPENT_LINK_CODES = new Set([
  "otp_expired",
  "email_link_invalid",
  "flow_state_expired",
  "flow_state_not_found",
]);

export type AuthLinkLocation = {
  hash: string;
  search: string;
};

export type AuthLinkStatus =
  /** No auth link params at all — an ordinary page visit. */
  | { kind: "none" }
  /** The URL carries credentials for supabase-js to exchange for a session. */
  | { kind: "credentials"; type: string | null }
  /** Supabase rejected the link. `message` is safe to show to the athlete. */
  | { kind: "error"; code: string | null; message: string };

/**
 * Merge the fragment and query params into a single lookup. The fragment wins
 * on conflict because that is where Supabase writes the authoritative result of
 * an implicit-flow redirect.
 */
export function readAuthLinkParams(location: AuthLinkLocation): URLSearchParams {
  const merged = new URLSearchParams(location.search.replace(/^\?/, ""));

  for (const [key, value] of new URLSearchParams(location.hash.replace(/^#/, ""))) {
    merged.set(key, value);
  }

  return merged;
}

function toMessage(code: string | null, description: string | null): string {
  if (code && SPENT_LINK_CODES.has(code)) {
    return AUTH_LINK_FEEDBACK.expired;
  }

  // Supabase's own wording for a spent link does not always come with a
  // machine-readable code, so fall back to matching the description.
  const normalizedDescription = description?.toLowerCase() ?? "";
  if (normalizedDescription.includes("expired") || normalizedDescription.includes("has already been used")) {
    return AUTH_LINK_FEEDBACK.expired;
  }

  return AUTH_LINK_FEEDBACK.invalid;
}

/**
 * Classify an auth email landing URL. Never surfaces the raw provider text —
 * `error_description` is attacker-influenced only in theory but is also written
 * for developers, so it is mapped to controlled copy like the rest of our auth
 * feedback.
 */
export function readAuthLinkStatus(location: AuthLinkLocation): AuthLinkStatus {
  const params = readAuthLinkParams(location);
  const error = params.get("error");
  const errorCode = params.get("error_code");

  if (error || errorCode) {
    const code = errorCode ?? error;
    return {
      kind: "error",
      code,
      message: toMessage(code, params.get("error_description")),
    };
  }

  if (params.has("access_token") || params.has("code")) {
    return { kind: "credentials", type: params.get("type") };
  }

  return { kind: "none" };
}

/**
 * Strip auth params from the address bar so tokens do not survive in history,
 * bookmarks, or the `Referer` header of any later navigation. supabase-js does
 * this for the fragment it consumes; the query half and rejected links are left
 * behind, so clean both.
 */
export function clearAuthLinkParams(): void {
  if (typeof window === "undefined" || !window.history?.replaceState) {
    return;
  }

  const url = new URL(window.location.href);
  const hadHash = readAuthLinkParams({ hash: url.hash, search: "" }).size > 0;
  let changed = hadHash;

  if (hadHash) {
    url.hash = "";
  }

  for (const key of ["access_token", "refresh_token", "code", "token", "type", "error", "error_code", "error_description", "expires_at", "expires_in", "provider_token", "provider_refresh_token"]) {
    if (url.searchParams.has(key)) {
      url.searchParams.delete(key);
      changed = true;
    }
  }

  if (changed) {
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }
}
