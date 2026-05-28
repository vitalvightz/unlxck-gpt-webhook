import type { GenerationJobResponse } from "@/lib/types";

export const MAX_PENDING_GENERATION_AGE_MS = 90 * 1000;
export const MAX_VISIBLE_GENERATION_AGE_MS = 10 * 60 * 1000;
export const MAX_STAGE1_INVOKED_VISIBLE_AGE_MS = 3 * 60 * 1000;

export function normalizeLegacyGenerationJobStatus(status: string | null | undefined): string {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "held_for_review") {
    return "review_required";
  }
  if (normalized === "publishable_with_flags") {
    return "completed";
  }
  return normalized;
}

export function isExpiredPendingGeneration(createdAt: string | null | undefined, nowMs = Date.now()): boolean {
  const createdAtMs = Date.parse(createdAt || "");
  if (!Number.isFinite(createdAtMs)) {
    return true;
  }
  return nowMs - createdAtMs > MAX_PENDING_GENERATION_AGE_MS;
}

export function isStaleVisibleGenerationJob(job: GenerationJobResponse, nowMs = Date.now()): boolean {
  const normalizedStatus = normalizeLegacyGenerationJobStatus(job.status);
  if (normalizedStatus !== "queued" && normalizedStatus !== "running") {
    return false;
  }

  const lastActivityMs = Date.parse(job.heartbeat_at || "") || Date.parse(job.started_at || "") || Date.parse(job.created_at || "");
  if (!Number.isFinite(lastActivityMs)) {
    return true;
  }

  const milestones = Array.isArray(job.progress_milestones) ? job.progress_milestones : [];
  const stage1Invoked = milestones.find((entry) => entry?.code === "stage1_planner_invoked");
  const stage1Finished = milestones.find((entry) => entry?.code === "stage1_planner_finished");
  if (stage1Invoked && !stage1Finished) {
    const invokedAtMs = Date.parse(stage1Invoked.at || "");
    if (Number.isFinite(invokedAtMs) && nowMs - invokedAtMs > MAX_STAGE1_INVOKED_VISIBLE_AGE_MS) {
      return true;
    }
  }
  return nowMs - lastActivityMs > MAX_VISIBLE_GENERATION_AGE_MS;
}

export function shouldBlockGenerateAutoStartForMatchingPayload(
  currentPayloadHash: string | null | undefined,
  completedPayloadHash: string | null | undefined,
): boolean {
  return (
    typeof currentPayloadHash === "string"
    && currentPayloadHash.length > 0
    && currentPayloadHash === completedPayloadHash
  );
}

export type MatchingPayloadGenerationAction =
  | { type: "redirect"; planId: string }
  | { type: "proceed" };

export function resolveMatchingPayloadGenerationAction(
  currentPayloadHash: string | null | undefined,
  completed: { planId: string | null; payloadHash: string | null } | null,
): MatchingPayloadGenerationAction {
  if (!completed || !shouldBlockGenerateAutoStartForMatchingPayload(currentPayloadHash, completed.payloadHash)) {
    return { type: "proceed" };
  }
  // Only block (redirect) when the cached plan is still openable. A matching
  // payload with no usable plan id (e.g. the plan was deleted/archived) must
  // proceed to a fresh generation rather than surface a stale duplicate state.
  return completed.planId && completed.planId.trim()
    ? { type: "redirect", planId: completed.planId }
    : { type: "proceed" };
}
