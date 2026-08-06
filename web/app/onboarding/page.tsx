import { Suspense } from "react";

import { PlanIntakeForm } from "@/components/plan-intake-form";
import { RequirePrivateTrialAck } from "@/components/private-trial-guard";

export default function OnboardingPage() {
  return (
    <Suspense fallback={null}>
      <RequirePrivateTrialAck>
        <PlanIntakeForm />
      </RequirePrivateTrialAck>
    </Suspense>
  );
}
