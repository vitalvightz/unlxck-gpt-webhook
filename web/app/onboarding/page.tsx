import { Suspense } from "react";

import { PlanIntakeForm } from "@/components/plan-intake-form";
import { RequireComplianceAcceptance } from "@/components/compliance-guard";

export default function OnboardingPage() {
  return (
    <Suspense fallback={null}>
      <RequireComplianceAcceptance>
        <PlanIntakeForm />
      </RequireComplianceAcceptance>
    </Suspense>
  );
}
