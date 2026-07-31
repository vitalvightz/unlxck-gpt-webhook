import { ApiError } from "@/lib/api";
import type { PlanActivationState } from "@/lib/types";

// The backend owns status, fight-date and athlete-local day eligibility. The
// frontend consumes only this derived state so list and detail views cannot
// drift from Today, Overview or the activation endpoint.
export const ACTIVE_PLAN_OVERLAP_MESSAGE =
  "This overlaps with your current active plan. Do you want to replace the current plan, pause it, or choose a new start date?";
export const ACTIVE_PLAN_OVERLAP_CODE = "active_plan_overlap";

export type ActivePlanOverlapAction = "replace" | "pause";

export function canSetActivePlan(
  activationState?: PlanActivationState | null,
): boolean {
  return activationState === "eligible";
}

export function isCompletedFightCamp(
  activationState?: PlanActivationState | null,
): boolean {
  return activationState === "fight_date_passed";
}

export function isArchivedPlan(status?: string | null): boolean {
  return status?.trim().toLowerCase() === "archived";
}

export function isActivePlanOverlapError(error: unknown): boolean {
  return error instanceof ApiError && error.code === ACTIVE_PLAN_OVERLAP_CODE;
}
