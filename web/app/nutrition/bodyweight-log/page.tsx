import { redirect } from "next/navigation";

import { BodyweightLogScreen } from "@/components/bodyweight-log-screen";
import { NUTRITION_DISABLED_REDIRECT, STANDALONE_NUTRITION_ENABLED } from "@/lib/beta-navigation";

export default function BodyweightLogPage() {
  if (!STANDALONE_NUTRITION_ENABLED) {
    redirect(NUTRITION_DISABLED_REDIRECT);
  }

  return <BodyweightLogScreen />;
}
