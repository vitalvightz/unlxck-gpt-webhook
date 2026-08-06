import { RequirePrivateTrialAck } from "@/components/private-trial-guard";
import { QuickBuildForm } from "@/components/quick-build-form";

export default function QuickBuildPage() {
  return (
    <RequirePrivateTrialAck>
      <QuickBuildForm />
    </RequirePrivateTrialAck>
  );
}
