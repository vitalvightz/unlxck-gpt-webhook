"use server";

import { cookies } from "next/headers";

import {
  isValidAccessCode,
  SIGNUP_ACCESS_COOKIE,
  SIGNUP_ACCESS_MAX_AGE_S,
  signupAccessToken,
} from "@/lib/signup-access";

/** `attempt` counts submissions so the screen can react to each wrong try. */
export type AccessCodeState = { status: "idle" | "error" | "granted"; attempt: number };

// A short pause on a wrong code makes guessing through the codes slow without
// being noticeable to someone who simply mistyped.
const WRONG_CODE_DELAY_MS = 700;

export async function submitAccessCode(previous: AccessCodeState, formData: FormData): Promise<AccessCodeState> {
  const attempt = previous.attempt + 1;
  const code = String(formData.get("code") ?? "");
  if (!isValidAccessCode(code)) {
    await new Promise((resolve) => setTimeout(resolve, WRONG_CODE_DELAY_MS));
    return { status: "error", attempt };
  }
  // Setting the cookie re-renders /signup, which now has access; the client
  // plays the unlock before showing the account form.
  (await cookies()).set(SIGNUP_ACCESS_COOKIE, signupAccessToken(), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: SIGNUP_ACCESS_MAX_AGE_S,
  });
  return { status: "granted", attempt };
}
