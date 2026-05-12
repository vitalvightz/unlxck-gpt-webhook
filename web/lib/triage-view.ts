import type { PlanDetail } from "@/lib/types";

export function hasTriageResumeApproval(plan: Pick<PlanDetail, "admin_outputs">): boolean {
  if (plan.admin_outputs?.stage2_status === "triage_resume_approved") {
    return true;
  }
  const whyLog = plan.admin_outputs?.why_log;
  if (!whyLog || typeof whyLog !== "object") {
    return false;
  }
  return Boolean((whyLog as Record<string, unknown>).triage_regeneration_cleared);
}

