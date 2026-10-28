import { cookies } from "next/headers";

import { SignupAccess } from "@/components/access-code-gate";
import { AuthForm } from "@/components/auth-form";
import { accessCodeShape, hasSignupAccess, SIGNUP_ACCESS_COOKIE } from "@/lib/signup-access";

// One screen: athlete is the only live role, so there is no role picker in front
// of the account form. Signup is invite-only: without the access cookie, the
// visitor first sees the access-code screen.
export default async function SignupPage({
  searchParams,
}: Readonly<{ searchParams: Promise<Record<string, string | string[] | undefined>> }>) {
  const unlocked = hasSignupAccess((await cookies()).get(SIGNUP_ACCESS_COOKIE)?.value);
  // ?invite=required: the visitor signed in with an account that has no
  // invite yet and was sent here (lib/signup-invite-guard.ts).
  const invite = (await searchParams).invite;
  const inviteRequired = (Array.isArray(invite) ? invite : [invite]).includes("required");
  return (
    <SignupAccess unlocked={unlocked} codeShape={accessCodeShape()} inviteRequired={inviteRequired}>
      {unlocked ? <AuthForm mode="signup" /> : null}
    </SignupAccess>
  );
}
