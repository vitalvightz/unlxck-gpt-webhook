import { ApiError } from "@/lib/api";

// Shared rule for whether a plan can be set as the athlete's active plan. A plan
// is eligible only once it is released to the athlete view ("ready" or
// "publishable_with_flags"); archived, triage, medical and review states are not
// eligible. Kept in one place so the plans list and the plan detail page agree.
export const ACTIVE_PLAN_OVERLAP_MESSAGE =
  "This overlaps with your current active plan. Do you want to replace the current plan, pause it, or choose a new start date?";
export const ACTIVE_PLAN_OVERLAP_CODE = "active_plan_overlap";

export type ActivePlanOverlapAction = "replace" | "pause";

export function canSetActivePlan(status?: string | null): boolean {
  const normalized = status?.trim().toLowerCase();
  return normalized === "ready" || normalized === "publishable_with_flags";
}

export function isArchivedPlan(status?: string | null): boolean {
  return status?.trim().toLowerCase() === "archived";
}

export function isActivePlanOverlapError(error: unknown): boolean {
  return error instanceof ApiError && error.code === ACTIVE_PLAN_OVERLAP_CODE;
}
