import { Suspense } from "react";

import { PlanIntakeForm } from "@/components/plan-intake-form";
import { RequireComplianceAcceptance } from "@/components/compliance-guard";
import { RequirePrivateTrialAck } from "@/components/private-trial-guard";

export default function OnboardingPage() {
  return (
    <Suspense fallback={null}>
      <RequireComplianceAcceptance>
        <RequirePrivateTrialAck>
          <PlanIntakeForm />
        </RequirePrivateTrialAck>
      </RequireComplianceAcceptance>
    </Suspense>
  );
}
