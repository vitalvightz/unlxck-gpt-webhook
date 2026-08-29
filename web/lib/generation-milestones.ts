import type { GenerationUiPhase } from "@/lib/generation-controller";
import type { ProgressMilestone } from "@/lib/types";

export type GenerationMilestone = {
  title: string;
  detail: string;
  variants?: string[];
};

export const GENERATION_MILESTONES: GenerationMilestone[] = [
  { title: "Reading athlete profile", detail: "Using style, goals, and fight context." },
  { title: "Checking fight timeline", detail: "Deciding whether this is GPP, SPP, taper, or open camp." },
  { title: "Building camp phase structure", detail: "Splitting the plan into the correct training blocks." },
  { title: "Mapping training availability", detail: "Matching sessions to available training days." },
  { title: "Matching fight format demands", detail: "Adjusting for rounds, duration, and combat demands." },
  { title: "Checking recovery profile", detail: "Matching the plan to your usual recovery speed." },
  {
    title: "Reviewing injury restrictions",
    detail: "Looking for areas that need protection or modification.",
    variants: ["Checking movement limitations", "Scanning for training restrictions", "Reviewing injury restrictions"],
  },
  { title: "Filtering unsafe exercises", detail: "Removing movements that conflict with restrictions." },
  { title: "Selecting strength priorities", detail: "Choosing the physical qualities with the highest return." },
  { title: "Balancing power and fatigue", detail: "Keeping explosive work effective without overloading the athlete." },
  {
    title: "Selecting conditioning focus",
    detail: "Matching energy systems to fight demands.",
    variants: ["Matching energy systems", "Building fight-specific conditioning", "Selecting conditioning focus"],
  },
  { title: "Matching drills to equipment", detail: "Using only the tools available to the athlete." },
  { title: "Sequencing training days", detail: "Placing hard, moderate, and recovery work in the right order." },
  { title: "Adjusting for recovery windows", detail: "Avoiding unnecessary overlap between demanding sessions." },
  { title: "Building weekly progression", detail: "Making the plan progress instead of repeating randomly." },
  { title: "Adding mobility and recovery work", detail: "Supporting movement quality and durability." },
  { title: "Reviewing nutrition context", detail: "Checking weight, target weight, and fight-week pressure." },
  { title: "Checking taper logic", detail: "Making sure late-camp work protects freshness." },
  {
    title: "Running final coach review",
    detail: "Checking the plan for logic, safety, and clarity.",
    variants: ["Reviewing coach logic", "Checking plan clarity", "Running final coach review"],
  },
  { title: "Saving finished plan", detail: "Preparing the final version for viewing." },
];

export type MilestoneView = {
  currentIndex: number;
  current: GenerationMilestone;
  completed: GenerationMilestone[];
};
const REAL_BACKEND_MILESTONE_OVERRIDES: Record<string, GenerationMilestone> = {
  job_loaded: {
    title: "Worker started",
    detail: "Worker loaded the generation job and is preparing request parsing.",
  },
};

const QUEUED_MAX_INDEX = 2;
const RUNNING_MAX_INDEX = 18;
const ROTATION_MS = 3_500;

function withVariant(milestone: GenerationMilestone, tick: number): GenerationMilestone {
  if (!milestone.variants?.length) {
    return milestone;
  }
  return {
    ...milestone,
    title: milestone.variants[tick % milestone.variants.length] || milestone.title,
  };
}

export function getGenerationMilestoneView(
  phase: GenerationUiPhase,
  startedAtMs: number | null,
  nowMs = Date.now(),
  realMilestones: ProgressMilestone[] = [],
): MilestoneView {
  const latestReal = realMilestones.length > 0 ? realMilestones[realMilestones.length - 1] : null;
  if (latestReal && typeof latestReal.code === "string" && latestReal.code.length > 0) {
    const override = REAL_BACKEND_MILESTONE_OVERRIDES[latestReal.code];
    if (override) {
      return { currentIndex: 0, current: override, completed: [] };
    }
    return {
      currentIndex: 0,
      current: {
        title: latestReal.label || "Generation update",
        detail: latestReal.detail || "Generation is in progress.",
      },
      completed: [],
    };
  }
  const elapsed = startedAtMs ? Math.max(0, nowMs - startedAtMs) : 0;
  const tick = Math.floor(elapsed / ROTATION_MS);

  if (phase === "failed") {
    return { currentIndex: 0, current: GENERATION_MILESTONES[0], completed: [] };
  }
  if (phase === "reconnecting") {
    return {
      currentIndex: 0,
      current: {
        title: "Reconnecting to generation job",
        detail: "Restoring progress from your saved request.",
      },
      completed: [],
    };
  }
  if (phase === "submitting") {
    return { currentIndex: 0, current: GENERATION_MILESTONES[0], completed: [] };
  }
  if (phase === "queued") {
    const currentIndex = Math.min(tick % (QUEUED_MAX_INDEX + 1), QUEUED_MAX_INDEX);
    return {
      currentIndex,
      current: withVariant(GENERATION_MILESTONES[currentIndex], tick),
      completed: GENERATION_MILESTONES.slice(0, currentIndex),
    };
  }
  if (phase === "running") {
    const currentIndex = Math.min(Math.floor(elapsed / ROTATION_MS), RUNNING_MAX_INDEX);
    return {
      currentIndex,
      current: withVariant(GENERATION_MILESTONES[currentIndex], tick),
      completed: GENERATION_MILESTONES.slice(0, currentIndex),
    };
  }

  return {
    currentIndex: 19,
    current: withVariant(GENERATION_MILESTONES[19], tick),
    completed: GENERATION_MILESTONES.slice(0, 19).map((milestone) => withVariant(milestone, tick)),
  };
}
