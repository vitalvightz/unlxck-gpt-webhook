import type { GenerationJobResponse } from "@/lib/types";

export const MAX_VISIBLE_GENERATION_AGE_MS = 30 * 60 * 1000;

export function isExpiredPendingGeneration(createdAt: string | null | undefined, nowMs = Date.now()): boolean {
  const createdAtMs = Date.parse(createdAt || "");
  if (!Number.isFinite(createdAtMs)) {
    return true;
  }
  return nowMs - createdAtMs > MAX_VISIBLE_GENERATION_AGE_MS;
}

export function isStaleVisibleGenerationJob(job: GenerationJobResponse, nowMs = Date.now()): boolean {
  if (job.status !== "queued" && job.status !== "running") {
    return false;
  }

  const lastActivityMs = Date.parse(job.heartbeat_at || "") || Date.parse(job.started_at || "") || Date.parse(job.created_at || "");
  if (!Number.isFinite(lastActivityMs)) {
    return true;
  }

  return nowMs - lastActivityMs > MAX_VISIBLE_GENERATION_AGE_MS;
}
