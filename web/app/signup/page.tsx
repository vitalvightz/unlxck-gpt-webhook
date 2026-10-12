import { AuthForm } from "@/components/auth-form";

// One screen: athlete is the only live role, so there is no role picker in front
// of the account form.
export default function SignupPage() {
  return <AuthForm mode="signup" />;
}
