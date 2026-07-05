export const PROFILE_REFRESH_FAILED_WARNING =
  "Profile refresh failed; plan generated from submitted intake only.";
export const PROFILE_REFRESH_FAILED_WARNING_CODE = "profile_refresh_failed_warning";

export const PROFILE_REFRESH_FAILED_BANNER_TITLE =
  "Profile refresh failed during generation.";

export const PROFILE_REFRESH_FAILED_BANNER_BODY =
  "This plan was generated from the submitted intake, but the saved athlete profile/onboarding data may still show older information. Review the latest intake before approving or editing this plan.";

type WarningCarrier = {
  warnings?: string[];
  progress_milestones?: Array<{ code?: string | null }>;
};

export function hasProfileRefreshFailedWarning(job: WarningCarrier | null | undefined): boolean {
  return (
    (job?.warnings?.includes(PROFILE_REFRESH_FAILED_WARNING) ?? false) ||
    (job?.progress_milestones?.some((milestone) => milestone.code === PROFILE_REFRESH_FAILED_WARNING_CODE) ?? false)
  );
}

// Athlete-facing copy: shorter and non-alarming, shown inline on the plan view.
// The admin banner above is for support/ops; this is for the athlete reading
// their own plan.
export const PROFILE_REFRESH_FAILED_ATHLETE_NOTICE =
  "Built from your latest intake. Your saved profile couldn't be refreshed and may be outdated.";

type PlanWithProfileRefreshFlag = {
  profile_refresh_failed?: boolean | null;
};

export function planHasProfileRefreshFailed(
  plan: PlanWithProfileRefreshFlag | null | undefined,
): boolean {
  return plan?.profile_refresh_failed === true;
}
