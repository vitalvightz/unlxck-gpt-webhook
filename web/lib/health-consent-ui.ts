import type { QuickBuildInput } from "@/lib/quick-build";
import type { PlanRequest } from "@/lib/types";

export const HEALTH_CONSENT_BLOCKED_MESSAGE =
  "Health data consent required. Manage it in Settings → Privacy.";

/** Remove health inputs from client state before it can be saved or generated. */
export function withoutIntakeHealthData(input: PlanRequest): PlanRequest {
  return {
    ...input,
    athlete: {
      ...input.athlete,
      weight_kg: null,
      target_weight_kg: null,
    },
    fatigue_level: "low",
    injuries: "",
    guided_injury: null,
    guided_injuries: [],
  };
}

export function withoutQuickBuildHealthData(input: QuickBuildInput): QuickBuildInput {
  return { ...input, injuries: "" };
}
