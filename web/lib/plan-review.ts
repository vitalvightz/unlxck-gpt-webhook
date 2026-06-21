import type { PlanSummary } from "@/lib/types";

export function isHeldForAdminReviewPlan(plan: Pick<PlanSummary, "status">): boolean {
  const status = plan.status?.trim().toLowerCase();
  return status === "held_for_review" || status === "review_required";
}

export function getPlanReviewReason(plan: Pick<PlanSummary, "status" | "review_reason">): string | null {
  if (!isHeldForAdminReviewPlan(plan)) {
    return null;
  }
  return plan.review_reason?.trim() || "Admin review is required before this plan can be released or set active.";
}
