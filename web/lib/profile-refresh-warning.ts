import type { AdminGenerationJobDiagnostic, GenerationJobResponse } from "@/lib/types";

export const PROFILE_REFRESH_FAILED_WARNING =
  "Profile refresh failed; plan generated from submitted intake only.";

export const PROFILE_REFRESH_FAILED_BANNER_TITLE =
  "Profile refresh failed during generation.";

export const PROFILE_REFRESH_FAILED_BANNER_BODY =
  "This plan was generated from the submitted intake, but the saved athlete profile/onboarding data may still show older information. Review the latest intake before approving or editing this plan.";

type WarningCarrier = Pick<GenerationJobResponse, "warnings"> | Pick<AdminGenerationJobDiagnostic, "warnings">;

export function hasProfileRefreshFailedWarning(job: WarningCarrier | null | undefined): boolean {
  return Array.isArray(job?.warnings) && job.warnings.includes(PROFILE_REFRESH_FAILED_WARNING);
}

