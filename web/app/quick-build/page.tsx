import { RequireComplianceAcceptance } from "@/components/compliance-guard";
import { QuickBuildForm } from "@/components/quick-build-form";

export default function QuickBuildPage() {
  return (
    <RequireComplianceAcceptance>
      <QuickBuildForm />
    </RequireComplianceAcceptance>
  );
}
