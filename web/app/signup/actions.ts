"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  isValidAccessCode,
  SIGNUP_ACCESS_COOKIE,
  SIGNUP_ACCESS_MAX_AGE_S,
  signupAccessToken,
} from "@/lib/signup-access";

export type AccessCodeState = { error: boolean };

// A short pause on a wrong code makes guessing through the codes slow without
// being noticeable to someone who simply mistyped.
const WRONG_CODE_DELAY_MS = 700;

export async function submitAccessCode(_previous: AccessCodeState, formData: FormData): Promise<AccessCodeState> {
  const code = String(formData.get("code") ?? "");
  if (!isValidAccessCode(code)) {
    await new Promise((resolve) => setTimeout(resolve, WRONG_CODE_DELAY_MS));
    return { error: true };
  }
  (await cookies()).set(SIGNUP_ACCESS_COOKIE, signupAccessToken(), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: SIGNUP_ACCESS_MAX_AGE_S,
  });
  redirect("/signup");
}
