import type { PlanDetail } from "@/lib/types";

function readObject(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  return value as Record<string, unknown>;
}

export function hasTriageResumeApproval(plan: Pick<PlanDetail, "admin_outputs">): boolean {
  if (plan.admin_outputs?.stage2_status === "triage_resume_approved") {
    return true;
  }

  const whyLog = readObject(plan.admin_outputs?.why_log);
  if (!whyLog) {
    return false;
  }

  if (Boolean(whyLog.triage_regeneration_cleared)) {
    return true;
  }

  const resumeOverride = readObject(whyLog.injury_triage_resume_override);
  if (resumeOverride?.bypassed_blocking === true) {
    return true;
  }

  const triageOriginal = readObject(whyLog.injury_triage_original);
  if (triageOriginal?.triage_resume_approved === true) {
    return true;
  }

  return false;
}
