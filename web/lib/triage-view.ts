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
  const status = String(plan.status || "").trim().toLowerCase();
  const mode = String(triageMode || "").trim().toLowerCase();
  const stage2Status = String(plan.admin_outputs?.stage2_status || "").trim().toLowerCase();
  const hasResumeApproval = hasTriageResumeApproval(plan);

  if (stage2Status === "triage_resume_approved") {
    return true;
  }

  if (status === "triage_blocked" && hasResumeApproval) {
    return true;
  }

  return (
    status === "triage_blocked" ||
    stage2Status === "triage_blocked" ||
    mode === "medical_hold" ||
    mode === "restricted_rehab_only"
  );
}