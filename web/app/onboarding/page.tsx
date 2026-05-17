import { Suspense } from "react";

import { PlanIntakeForm } from "@/components/plan-intake-form";

export default function OnboardingPage() {
  return (
    <Suspense fallback={null}>
      <PlanIntakeForm />
    </Suspense>
  );
}
