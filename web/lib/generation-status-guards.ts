import type { GenerationJobResponse } from "@/lib/types";

export const MAX_PENDING_GENERATION_AGE_MS = 90 * 1000;
export const MAX_VISIBLE_GENERATION_AGE_MS = 10 * 60 * 1000;
export const MAX_STAGE1_INVOKED_VISIBLE_AGE_MS = 3 * 60 * 1000;

export function isExpiredPendingGeneration(createdAt: string | null | undefined, nowMs = Date.now()): boolean {
  const createdAtMs = Date.parse(createdAt || "");
  if (!Number.isFinite(createdAtMs)) {
    return true;
  }
  return nowMs - createdAtMs > MAX_PENDING_GENERATION_AGE_MS;
}

export function isStaleVisibleGenerationJob(job: GenerationJobResponse, nowMs = Date.now()): boolean {
  if (job.status !== "queued" && job.status !== "running") {
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

export function shouldBlockGenerateAutoStart(latestPlanId: string | null | undefined): boolean {
  return typeof latestPlanId === "string" && latestPlanId.trim().length > 0;
}
