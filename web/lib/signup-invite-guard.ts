/**
 * Signup is invite-only, but Google sign-in on /login creates an account for
 * anyone. Before the app loads a profile for a brand-new account (or one that
 * was turned away earlier), it checks for the unlock cookie set by the access
 * code screen; without it the visitor is signed out and sent to that screen.
 *
 * This closes the accidental route in the browser. It is not a server-side
 * lock: a determined caller can still reach the API directly.
 */
export const NEW_ACCOUNT_WINDOW_MS = 10 * 60 * 1000;
export const INVITE_PENDING_FLAG = "invite_pending";
export const INVITE_REQUIRED_HREF = "/signup?invite=required";

export type InviteGuardSession = { created_at?: string | null; invite_pending?: boolean };

/** True for an account created in the last few minutes, or one turned away before. */
export function needsInviteCheck(session: InviteGuardSession, now: number = Date.now()): boolean {
  if (session.invite_pending) return true;
  const created = session.created_at ? Date.parse(session.created_at) : Number.NaN;
  return Number.isFinite(created) && now - created < NEW_ACCOUNT_WINDOW_MS;
}
