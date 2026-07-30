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

export function markPasswordRecovery(userId: string): void {
  const storage = getStorage();
  if (!storage || !userId) {
    return;
  }
  const marker: PasswordRecoveryMarker = { userId, at: Date.now() };
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(marker));
  } catch {
    // Storage full or blocked. The athlete can still use a link that lands
    // directly on /reset-password, so fail quietly rather than break the page.
  }
}

/**
 * The live recovery marker, or null when absent, unreadable, malformed, or
 * past its TTL. Callers must still check it against the session's user.
 */
export function readPasswordRecovery(): PasswordRecoveryMarker | null {
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
  // A future timestamp means a tampered or clock-skewed marker; refuse it too.
  const age = Date.now() - at;
  if (age < 0 || age > RECOVERY_TTL_MS) {
    return null;
  }

  return { userId, at };
}

/** True when a live marker vouches for exactly this user. */
export function hasPasswordRecoveryFor(userId: string | null | undefined): boolean {
  if (!userId) {
    return false;
  }
  return readPasswordRecovery()?.userId === userId;
}

export function clearPasswordRecovery(): void {
  const storage = getStorage();
  if (!storage) {
    return;
  }
  try {
    storage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing to do — a stale marker still expires on its own.
  }
}

export const PASSWORD_RECOVERY_STORAGE_KEY = STORAGE_KEY;
export const PASSWORD_RECOVERY_TTL_MS = RECOVERY_TTL_MS;
