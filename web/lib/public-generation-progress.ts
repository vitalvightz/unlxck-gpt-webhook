import type { GenerationUiPhase } from "./generation-controller";
import type { ProgressMilestone } from "./types";

export const PUBLIC_CAMP_MILESTONES = [
  { code: "profile_ready", title: "Profile ready", detail: "Goals and training needs reviewed.", anchor: 18 },
  { code: "designing_camp", title: "Designing your camp", detail: "Training phases and workload being organised.", anchor: 42 },
  { code: "building_sessions", title: "Building your sessions", detail: "Exercises and session details being assembled.", anchor: 68 },
  { code: "final_checks", title: "Final checks", detail: "Safety and plan quality being verified.", anchor: 90 },
  { code: "camp_ready", title: "Camp ready", detail: "Your plan is ready to open.", anchor: 100 },
] as const;

export function getPublicMilestoneIndex(phase: GenerationUiPhase, milestones: ProgressMilestone[]): number {
  if (phase === "finalizing") return PUBLIC_CAMP_MILESTONES.length - 1;
  let index = 0;
  for (const milestone of milestones) {
    const found = PUBLIC_CAMP_MILESTONES.findIndex((item) => item.code === milestone.code);
    if (found >= 0) index = Math.max(index, found);
  }
  return index;
}

export function getPublicProgress(
  phase: GenerationUiPhase,
  milestones: ProgressMilestone[],
  startedAtMs: number | null,
  nowMs: number,
): number {
  if (phase === "finalizing") return 100;
  if (phase === "failed" || phase === "review_paused" || phase === "already_generated") {
    return PUBLIC_CAMP_MILESTONES[getPublicMilestoneIndex(phase, milestones)]?.anchor ?? 0;
  }
  const index = getPublicMilestoneIndex(phase, milestones);
  const anchor = PUBLIC_CAMP_MILESTONES[index].anchor;
  const nextAnchor = PUBLIC_CAMP_MILESTONES[Math.min(index + 1, 3)].anchor;
  const elapsed = startedAtMs ? Math.max(0, nowMs - startedAtMs) : 0;
  // Time only interpolates within the current real milestone. It cannot complete
  // another landmark and deliberately slows to a hold below the next anchor.
  const eased = 1 - Math.exp(-elapsed / 75_000);
  return Math.min(94, anchor + (nextAnchor - anchor) * 0.72 * eased);
}
