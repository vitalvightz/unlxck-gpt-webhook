import { cookies } from "next/headers";

import { SignupAccess } from "@/components/access-code-gate";
import { AuthForm } from "@/components/auth-form";
import { accessCodeShape, hasSignupAccess, SIGNUP_ACCESS_COOKIE } from "@/lib/signup-access";

// One screen: athlete is the only live role, so there is no role picker in front
// of the account form. Signup is invite-only: without the access cookie, the
// visitor first sees the access-code screen.
export default async function SignupPage() {
  const unlocked = hasSignupAccess((await cookies()).get(SIGNUP_ACCESS_COOKIE)?.value);
  return (
    <SignupAccess unlocked={unlocked} codeShape={accessCodeShape()}>
      {unlocked ? <AuthForm mode="signup" /> : null}
    </SignupAccess>
  );
}
