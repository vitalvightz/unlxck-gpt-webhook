// Proof that the athlete arrived through a verified password recovery link,
// carried across a navigation.
//
// Supabase decides which allow-listed URL a recovery link lands on, and it
// falls back to the project Site URL whenever `redirect_to` is not allow
// listed. That routinely drops a recovery session somewhere other than
// /reset-password, where supabase-js consumes the tokens, the athlete is simply
// signed in, and the intent to set a new password is lost. Recording the event
// lets /reset-password pick the flow back up.
//
// SECURITY: the marker is written *only* from a genuine PASSWORD_RECOVERY
// event, which supabase-js emits only after it has validated and stored a
// recovery session. Never derive it from URL contents — that is exactly the
// bypass that let `?code=arbitrary` plus an existing session open the form.
// sessionStorage is same-origin and tab-scoped, and nothing in a link can set
// it.

const STORAGE_KEY = "unlxck.password-recovery";

// Long enough to survive the redirect and a slow page load, short enough that a
// marker cannot linger usefully in a tab left open.
const RECOVERY_TTL_MS = 15 * 60 * 1000;

export type PasswordRecoveryMarker = {
  /** The user the recovery session belongs to. */
  userId: string;
  /** When the PASSWORD_RECOVERY event was observed, epoch milliseconds. */
  at: number;
};

// In-memory mirror, matching the pattern in lib/generation-intent.ts.
// sessionStorage can be unavailable or throw (private browsing, strict storage
// policies, the in-app browsers email clients open links in). Without this, a
// blocked write would leave the athlete redirected to a form that then refuses
// them for "missing" proof — a dead end reachable only by people whose browser
// is already restrictive. The event and the reset page share one client-side
// runtime, so a module-level value carries the proof across that navigation;
// sessionStorage only adds durability across a reload.
let memoryMarker: PasswordRecoveryMarker | null = null;

function getStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.sessionStorage;
  } catch {
    // Private mode or storage disabled by policy.
    return null;
  }
}

function isLive(marker: PasswordRecoveryMarker | null): marker is PasswordRecoveryMarker {
  if (!marker) {
    return false;
  }
  // A future timestamp means a tampered or clock-skewed marker; refuse it too.
  const age = Date.now() - marker.at;
  return age >= 0 && age <= RECOVERY_TTL_MS;
}

export function markPasswordRecovery(userId: string): void {
  if (typeof window === "undefined" || !userId) {
    return;
  }

  const marker: PasswordRecoveryMarker = { userId, at: Date.now() };
  memoryMarker = marker;

  try {
    getStorage()?.setItem(STORAGE_KEY, JSON.stringify(marker));
  } catch {
    // The in-memory mirror above still carries the proof through the redirect.
  }
}

/**
 * The live recovery marker, or null when absent, unreadable, malformed, or
 * past its TTL. Callers must still check it against the session's user.
 */
export function readPasswordRecovery(): PasswordRecoveryMarker | null {
  if (typeof window === "undefined") {
    // Never trust module state on the server: it is shared across requests.
    return null;
  }

  if (isLive(memoryMarker)) {
    return memoryMarker;
  }

  const storage = getStorage();
  if (!storage) {
    return null;
  }

  let raw: string | null;
  try {
    raw = storage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
  if (!raw) {
    return null;
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }

  if (typeof parsed !== "object" || parsed === null) {
    return null;
  }
  const { userId, at } = parsed as Partial<PasswordRecoveryMarker>;
  if (typeof userId !== "string" || !userId || typeof at !== "number" || !Number.isFinite(at)) {
    return null;
  }

  const stored: PasswordRecoveryMarker = { userId, at };
  return isLive(stored) ? stored : null;
}

/** True when a live marker vouches for exactly this user. */
export function hasPasswordRecoveryFor(userId: string | null | undefined): boolean {
  if (!userId) {
    return false;
  }
  return readPasswordRecovery()?.userId === userId;
}

export function clearPasswordRecovery(): void {
  // Clear the mirror first and unconditionally: it is the channel that works
  // when storage does not, so it must not survive a spent recovery.
  memoryMarker = null;
  try {
    getStorage()?.removeItem(STORAGE_KEY);
  } catch {
    // Nothing to do — a stale marker still expires on its own.
  }
}

export const PASSWORD_RECOVERY_STORAGE_KEY = STORAGE_KEY;
export const PASSWORD_RECOVERY_TTL_MS = RECOVERY_TTL_MS;
