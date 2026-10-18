import { RequireAuth } from "@/components/auth-guard";
import { StartingPathScreen } from "@/components/starting-path-screen";

export default function GetStartedPage() {
  return <RequireAuth><StartingPathScreen /></RequireAuth>;
}
