import { redirect } from "next/navigation";

import { NutritionWorkspaceScreen } from "@/components/nutrition-workspace-screen";
import { NUTRITION_DISABLED_REDIRECT, STANDALONE_NUTRITION_ENABLED } from "@/lib/beta-navigation";

export default function NutritionPage() {
  // Standalone Nutrition is disabled for beta. A direct hit is bounced to
  // Overview rather than exposing the retired workspace.
  if (!STANDALONE_NUTRITION_ENABLED) {
    redirect(NUTRITION_DISABLED_REDIRECT);
  }

  return <NutritionWorkspaceScreen />;
}
