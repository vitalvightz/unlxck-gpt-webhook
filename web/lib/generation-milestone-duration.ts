// How long each backend milestone actually took.
//
// The build feed used to print the milestone's offset from the job start
// ("Stage 2 model call started — +1m 06s") and then leave that number frozen
// while the stage kept running. Next to a total-elapsed clock that kept
// climbing, the two readings looked unsynchronised: nothing on screen ever said
// how long the *current* stage had been going.
//
// Each row now reports a duration: the gap to the next milestone, or — for the
// stage still in flight — the gap to now, which freezes on the job's terminal
// timestamp once it lands.

import { formatElapsed } from "@/lib/generation-elapsed";
import type { ProgressMilestone } from "@/lib/types";

export type MilestoneDurationView = {
  milestone: ProgressMilestone;
  startedAtMs: number | null;
  durationMs: number | null;
  // True only for the last milestone of a job that has not finished yet.
  isRunning: boolean;
  // "3m 46s" — bare duration, no prefix.
  durationLabel: string | null;
  // "+1m 06s" — offset from the start of the build, kept as secondary context.
  offsetLabel: string | null;
};

export type MilestoneDurationOptions = {
  nowMs?: number;
  // Terminal instant of the job (`completed_at ?? updated_at`), or null while
  // the job is live.
  endedAtMs?: number | null;
  // Job start, used for the secondary offset label.
  startedAtMs?: number | null;
};

function parseMilestoneAtMs(milestone: ProgressMilestone | undefined): number | null {
  const parsed = Date.parse(milestone?.at || "");
  return Number.isFinite(parsed) ? parsed : null;
}

function formatOffset(offsetMs: number): string {
  return `+${formatElapsed(offsetMs)}`;
}

export function resolveMilestoneDurations(
  milestones: ProgressMilestone[],
  { nowMs = Date.now(), endedAtMs = null, startedAtMs = null }: MilestoneDurationOptions = {},
): MilestoneDurationView[] {
  const hasEnded = endedAtMs !== null && Number.isFinite(endedAtMs);
  const jobEndMs = hasEnded ? (endedAtMs as number) : nowMs;

  return milestones.map((milestone, index) => {
    const milestoneStartMs = parseMilestoneAtMs(milestone);

    // The next milestone that carries a usable timestamp ends this one. A
    // milestone the backend wrote without an `at` must not swallow the stage.
    let nextStartMs: number | null = null;
    for (let cursor = index + 1; cursor < milestones.length; cursor += 1) {
      const candidate = parseMilestoneAtMs(milestones[cursor]);
      if (candidate !== null) {
        nextStartMs = candidate;
        break;
      }
    }

    // A row with no timestamp of its own cannot be the stage in flight — it has
    // no duration to count. Without this guard a trailing untimed milestone
    // claimed "running" alongside the real last timed stage, so two rows were
    // live at once and the untimed one took the latest-row marker.
    const isRunning = milestoneStartMs !== null && nextStartMs === null && !hasEnded;
    const endMs = nextStartMs ?? jobEndMs;
    const durationMs =
      milestoneStartMs === null ? null : Math.max(0, endMs - milestoneStartMs);
    const offsetMs =
      milestoneStartMs === null || startedAtMs === null || !Number.isFinite(startedAtMs)
        ? null
        : Math.max(0, milestoneStartMs - startedAtMs);

    return {
      milestone,
      startedAtMs: milestoneStartMs,
      durationMs,
      isRunning,
      durationLabel: durationMs === null ? null : formatElapsed(durationMs),
      offsetLabel: offsetMs === null ? null : formatOffset(offsetMs),
    };
  });
}

/**
 * The full row label used by the build feed: "Stage 2 model call — running for
 * 3m 46s" while in flight, "Stage 2 model call — 4m 39s" once the stage (or the
 * job) has finished.
 */
export function formatMilestoneDurationLabel(view: MilestoneDurationView): string | null {
  if (view.durationLabel === null) {
    return null;
  }
  return view.isRunning ? `running for ${view.durationLabel}` : view.durationLabel;
}
