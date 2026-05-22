import type { PlanDetail } from "@/lib/types";

function readObject(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
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

  if (whyLog.triage_regeneration_cleared === true) {
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

export function shouldShowTriageBlockedState(
  plan: Pick<PlanDetail, "status" | "admin_outputs">,
  triageMode: string | null | undefined,
): boolean {
  const mode = String(triageMode || "").trim().toLowerCase();
  const isBlockedByPlanState =
    plan.status === "triage_blocked" ||
    plan.admin_outputs?.stage2_status === "triage_blocked" ||
    mode === "medical_hold" ||
    mode === "restricted_rehab_only";

  return isBlockedByPlanState && !hasTriageResumeApproval(plan);
}
