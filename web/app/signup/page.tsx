import { cookies } from "next/headers";

import { AccessCodeGate } from "@/components/access-code-gate";
import { AuthForm } from "@/components/auth-form";
import { hasSignupAccess, SIGNUP_ACCESS_COOKIE } from "@/lib/signup-access";

// One screen: athlete is the only live role, so there is no role picker in front
// of the account form. Signup is invite-only: without the access cookie, the
// visitor first sees the access-code screen.
export default async function SignupPage() {
  const access = (await cookies()).get(SIGNUP_ACCESS_COOKIE)?.value;
  return hasSignupAccess(access) ? <AuthForm mode="signup" /> : <AccessCodeGate />;
}
