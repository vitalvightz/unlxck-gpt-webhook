// In-tab handoff between the two generation state machines.
//
// The /generate controller and the global status ribbon are separate
// components with separate polling loops. The controller learns a job reached
// `completed` / `review_required` / `failed` first, and clears the shared
// pending-generation record from localStorage as part of finishing. A
// same-tab localStorage write does NOT fire a `storage` event, and the ribbon's
// poll only ran while that record existed — so the ribbon could never learn the
// job was over and its timer rolled forever.
//
// The controller now publishes the terminal job payload on the window, and the
// provider consumes it immediately instead of waiting up to a poll interval
// (or forever).

import { normalizeLegacyGenerationJobStatus } from "@/lib/generation-status-guards";
import type { GenerationJobResponse } from "@/lib/types";

export const GENERATION_TERMINAL_EVENT = "unlxck:generation-terminal";

export function isTerminalGenerationStatus(status: string | null | undefined): boolean {
  const normalized = normalizeLegacyGenerationJobStatus(status);
  return normalized === "completed" || normalized === "review_required" || normalized === "failed";
}

/**
 * The instant the backend says the job stopped. `completed_at` is the precise
 * value; `updated_at` is the fallback for jobs whose terminal write did not set
 * it. Returns `fallbackMs` when neither timestamp parses, so a terminal job can
 * still freeze its timer rather than ticking on forever.
 */
export function resolveGenerationEndedAtMs(
  job: { completed_at?: string | null; updated_at?: string | null } | null | undefined,
  fallbackMs: number | null = null,
): number | null {
  if (!job) {
    return fallbackMs;
  }

  const parsed = Date.parse(job.completed_at || job.updated_at || "");
  return Number.isFinite(parsed) ? parsed : fallbackMs;
}

export function publishGenerationTerminalJob(job: GenerationJobResponse | null | undefined): void {
  if (typeof window === "undefined" || !job?.job_id) {
    return;
  }

  window.dispatchEvent(
    new CustomEvent<GenerationJobResponse>(GENERATION_TERMINAL_EVENT, { detail: job }),
  );
}

export function subscribeGenerationTerminalJob(
  handler: (job: GenerationJobResponse) => void,
): () => void {
  if (typeof window === "undefined") {
    return () => {};
  }

  const listener = (event: Event) => {
    const job = (event as CustomEvent<GenerationJobResponse>).detail;
    if (job?.job_id) {
      handler(job);
    }
  };

  window.addEventListener(GENERATION_TERMINAL_EVENT, listener);
  return () => window.removeEventListener(GENERATION_TERMINAL_EVENT, listener);
}
