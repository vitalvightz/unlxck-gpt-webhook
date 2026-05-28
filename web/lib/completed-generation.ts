export const COMPLETED_GENERATION_KEY = "unlxck:completed-generation:self";

export type CompletedGenerationRecord = {
  planId: string | null;
  payloadHash: string | null;
};

export function parseCompletedGeneration(raw: string | null): CompletedGenerationRecord | null {
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as { payloadHash?: unknown; planId?: unknown };
    const planId = typeof parsed.planId === "string" && parsed.planId.trim() ? parsed.planId : null;
    const payloadHash = typeof parsed.payloadHash === "string" ? parsed.payloadHash : null;
    if (!planId && !payloadHash) {
      return null;
    }
    return { planId, payloadHash };
  } catch {
    return null;
  }
}

export function shouldClearCompletedGenerationForDeletedPlan(
  raw: string | null,
  deletedPlanId: string | null | undefined,
): boolean {
  if (!raw || !deletedPlanId) {
    return false;
  }
  try {
    const parsed = JSON.parse(raw) as { planId?: unknown };
    return typeof parsed.planId === "string" && parsed.planId === deletedPlanId;
  } catch {
    return false;
  }
}

export function clearCompletedGenerationForDeletedPlan(deletedPlanId: string | null | undefined): void {
  if (typeof window === "undefined") {
    return;
  }
  const raw = window.localStorage.getItem(COMPLETED_GENERATION_KEY);
  if (shouldClearCompletedGenerationForDeletedPlan(raw, deletedPlanId)) {
    window.localStorage.removeItem(COMPLETED_GENERATION_KEY);
  }
}
