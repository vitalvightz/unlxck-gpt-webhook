import { createHash, timingSafeEqual } from "node:crypto";

/**
 * Invite-only signup. The access code lives only on the server (env
 * SIGNUP_ACCESS_CODE, falling back to the launch code) and is never sent to
 * the browser. Entering it sets an httpOnly cookie holding a hash of the code,
 * so changing the code also locks out old cookies.
 *
 * This gates the signup page, not account creation itself: it keeps the
 * invite feel for normal visitors but is not a security boundary.
 */
export const SIGNUP_ACCESS_COOKIE = "unlxck_signup_access";
export const SIGNUP_ACCESS_MAX_AGE_S = 60 * 60 * 24 * 180;
const DEFAULT_SIGNUP_ACCESS_CODE = "63839";

function expectedCode(): string {
  return process.env.SIGNUP_ACCESS_CODE?.trim() || DEFAULT_SIGNUP_ACCESS_CODE;
}

/** Digits and letters only, so "63 839" or a pasted code with spaces still works. */
export function normalizeAccessCode(input: string): string {
  return input.replace(/[^0-9a-z]/gi, "").toUpperCase();
}

export function isValidAccessCode(input: string): boolean {
  const given = Buffer.from(normalizeAccessCode(input));
  const expected = Buffer.from(normalizeAccessCode(expectedCode()));
  return given.length === expected.length && timingSafeEqual(given, expected);
}

/**
 * The code's shape, for drawing one box per character and picking the
 * keypad. Length and digits-only are safe to send; the code itself is not.
 */
export function accessCodeShape(): { length: number; numeric: boolean } {
  const code = normalizeAccessCode(expectedCode());
  return { length: code.length, numeric: /^\d+$/.test(code) };
}

/** The cookie value for the current code. */
export function signupAccessToken(): string {
  return createHash("sha256").update(`unlxck-signup:${normalizeAccessCode(expectedCode())}`).digest("hex");
}

export function hasSignupAccess(cookieValue: string | undefined): boolean {
  return Boolean(cookieValue) && cookieValue === signupAccessToken();
}
