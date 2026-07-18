import { AuthForm } from "@/components/auth-form";
import { InstallUnlxck } from "@/components/install-unlxck";

export default function LoginPage() {
  return <AuthForm mode="login" footerSlot={<InstallUnlxck variant="inline" />} />;
}
