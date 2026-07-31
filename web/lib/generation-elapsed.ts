// Single source of truth for "how long has this build been running".
//
// The build screen and the global ribbon each used to own a private
// `formatElapsed` plus a private `Date.now()` ticker, so the two clocks could
// disagree — and neither of them knew how to stop. Elapsed time is now derived
// from the backend's own timestamps: it runs off `nowMs` only while the job is
// live, and freezes on `endedAtMs` the moment the job reaches a terminal state.

export type GenerationElapsedInput = {
  startedAtMs: number | null;
  // Terminal instant taken from the job (`completed_at ?? updated_at`). Null
  // while the job is still live.
  endedAtMs?: number | null;
  nowMs?: number;
};

export function formatElapsed(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  if (minutes === 0) {
    return `${seconds}s`;
  }

  return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
}

export function resolveGenerationElapsedMs({
  startedAtMs,
  endedAtMs = null,
  nowMs = Date.now(),
}: GenerationElapsedInput): number | null {
  if (startedAtMs === null || !Number.isFinite(startedAtMs)) {
    return null;
  }

  const referenceMs = endedAtMs !== null && Number.isFinite(endedAtMs) ? endedAtMs : nowMs;
  // Backend clock skew can put a terminal timestamp marginally before the
  // create timestamp; a negative duration is never the truth, so clamp.
  return Math.max(0, referenceMs - startedAtMs);
}

export function formatGenerationElapsedLabel(input: GenerationElapsedInput): string | null {
  const elapsedMs = resolveGenerationElapsedMs(input);
  return elapsedMs === null ? null : formatElapsed(elapsedMs);
}

export function isGenerationElapsedFrozen(endedAtMs: number | null | undefined): boolean {
  return endedAtMs !== null && endedAtMs !== undefined && Number.isFinite(endedAtMs);
}

// The passive ribbon renders a job the provider is no longer tracking, so it
// has no `startedAtMs`/`endedAtMs` in context to read — it has to recover the
// window from the job row itself.
export type GenerationJobTiming = {
  started_at?: string | null;
  created_at?: string | null;
  completed_at?: string | null;
  updated_at?: string | null;
};

function firstParsedMs(values: (string | null | undefined)[]): number | null {
  for (const value of values) {
    const parsed = Date.parse(value || "");
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
}

/**
 * The build window of a job row: it started when the worker picked it up
 * (`started_at`, falling back to when it was created), and ended when it
 * finished (`completed_at`, falling back to its last write). Both ends are
 * fixed backend values, so the total this produces cannot drift.
 */
export function resolveJobElapsedWindow(job: GenerationJobTiming | null | undefined): {
  startedAtMs: number | null;
  endedAtMs: number | null;
} {
  if (!job) {
    return { startedAtMs: null, endedAtMs: null };
  }

  return {
    startedAtMs: firstParsedMs([job.started_at, job.created_at]),
    endedAtMs: firstParsedMs([job.completed_at, job.updated_at]),
  };
}

export function formatJobElapsedLabel(
  job: GenerationJobTiming | null | undefined,
  nowMs = Date.now(),
): string | null {
  const { startedAtMs, endedAtMs } = resolveJobElapsedWindow(job);
  if (startedAtMs === null) {
    return null;
  }
  return formatGenerationElapsedLabel({ startedAtMs, endedAtMs, nowMs });
}
