import {
  EQUIPMENT_ACCESS_OPTIONS,
  KEY_GOAL_OPTIONS,
  TRAINING_AVAILABILITY_OPTIONS,
  WEAK_AREA_OPTIONS,
  type IntakeOption,
} from "@/lib/intake-options";
import {
  getPerformanceFocusOptionAvailability,
  type DaysOutContext,
  type PerformanceFocusGroup,
} from "@/lib/days-out-policy";

export type EquipmentPresetKey = "home" | "basic_gym" | "full_gym";
export type TrainingPresetKey = "three_days" | "four_days" | "five_days";
export type FocusPresetKey =
  | "explosive_power"
  | "strength_base"
  | "gas_tank"
  | "speed_footwork"
  | "mobility_control"
  | "weight_cut_support"
  | "return_from_injury"
  | "technical_sharpness";

export type EquipmentPreset = {
  key: EquipmentPresetKey;
  label: string;
  description: string;
  equipment_access: string[];
};

export type TrainingPreset = {
  key: TrainingPresetKey;
  label: string;
  description: string;
  training_availability: string[];
  weekly_training_frequency: number;
};

export type FocusPreset = {
  key: FocusPresetKey;
  label: string;
  description: string;
  goals: string[];
  weak_areas: string[];
};

export type FocusPresetSelectionLimits = {
  goalLimit: number;
  weakAreaLimit: number;
  sharedLimit: number | null;
  daysOutCtx: DaysOutContext;
};

export type FocusPresetSelections = {
  key_goals: string[];
  weak_areas: string[];
};

export const EQUIPMENT_PRESETS: EquipmentPreset[] = [
  {
    key: "home",
    label: "Home fight kit",
    description: "Bands, bag, partner, med ball",
    equipment_access: ["bands", "heavy_bag", "partner", "medicine_ball"],
  },
  {
    key: "basic_gym",
    label: "Basic gym",
    description: "Dumbbells, barbell, bag",
    equipment_access: [
      "dumbbells",
      "kettlebells",
      "barbell",
      "pullup_bar",
      "bands",
      "heavy_bag",
      "thai_pads",
    ],
  },
  {
    key: "full_gym",
    label: "Full gym",
    description: "Everything available",
    equipment_access: EQUIPMENT_ACCESS_OPTIONS
      .map((option) => option.value)
      .filter((value) => value !== "partner"),
  },
];

export const FOCUS_PRESETS: FocusPreset[] = [
  {
    key: "explosive_power",
    label: "Explosive power",
    description: "Power, speed, strength",
    goals: ["power", "speed", "strength", "skill_refinement"],
    weak_areas: ["power", "trunk_strength", "coordination", "speed"],
  },
  {
    key: "strength_base",
    label: "Strength base",
    description: "Strength, power, recovery",
    goals: ["strength", "power", "recovery"],
    weak_areas: ["strength", "trunk_strength", "balance", "mobility"],
  },
  {
    key: "gas_tank",
    label: "Gas tank",
    description: "Conditioning, recovery",
    goals: ["conditioning", "recovery", "skill_refinement"],
    weak_areas: ["gas_tank", "mobility", "coordination"],
  },
  {
    key: "speed_footwork",
    label: "Speed & footwork",
    description: "Speed, footwork, balance",
    goals: ["speed", "skill_refinement", "power"],
    weak_areas: ["footwork", "coordination", "balance", "speed"],
  },
  {
    key: "mobility_control",
    label: "Mobility & control",
    description: "Mobility, balance, trunk",
    goals: ["mobility", "recovery", "strength"],
    weak_areas: ["mobility", "balance", "coordination", "trunk_strength"],
  },
  {
    key: "weight_cut_support",
    label: "Weight cut support",
    description: "Cut support, recovery",
    goals: ["weight_cut", "recovery", "skill_refinement", "conditioning"],
    weak_areas: ["gas_tank", "mobility", "balance", "coordination"],
  },
  {
    key: "return_from_injury",
    label: "Return from injury",
    description: "Recovery, mobility, strength",
    goals: ["recovery", "mobility", "strength", "skill_refinement"],
    weak_areas: ["mobility", "balance", "trunk_strength", "coordination"],
  },
  {
    key: "technical_sharpness",
    label: "Technical sharpness",
    description: "Skill, speed, timing",
    goals: ["skill_refinement", "speed", "power"],
    weak_areas: ["coordination", "footwork", "balance", "speed"],
  },
];

export const TRAINING_PRESETS: TrainingPreset[] = [
  {
    key: "three_days",
    label: "3 days",
    description: "Mon, Wed, Fri",
    training_availability: ["Monday", "Wednesday", "Friday"],
    weekly_training_frequency: 3,
  },
  {
    key: "four_days",
    label: "4 days",
    description: "Mon, Tue, Thu, Fri",
    training_availability: ["Monday", "Tuesday", "Thursday", "Friday"],
    weekly_training_frequency: 4,
  },
  {
    key: "five_days",
    label: "5 days",
    description: "Mon, Tue, Thu, Fri, Sat",
    training_availability: ["Monday", "Tuesday", "Thursday", "Friday", "Saturday"],
    weekly_training_frequency: 5,
  },
];

function sameStringSet(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const seen = new Set(a);
  for (const value of b) {
    if (!seen.has(value)) return false;
  }
  return true;
}

export function matchesEquipmentPreset(equipmentAccess: string[]): EquipmentPresetKey | null {
  for (const preset of EQUIPMENT_PRESETS) {
    if (sameStringSet(preset.equipment_access, equipmentAccess)) {
      return preset.key;
    }
  }
  return null;
}

export function matchesTrainingPreset(
  trainingAvailability: string[],
  weeklyTrainingFrequency: number,
): TrainingPresetKey | null {
  for (const preset of TRAINING_PRESETS) {
    if (
      preset.weekly_training_frequency === weeklyTrainingFrequency
      && sameStringSet(preset.training_availability, trainingAvailability)
    ) {
      return preset.key;
    }
  }
  return null;
}

function hasSharedFocusSpace(selections: FocusPresetSelections, sharedLimit: number | null): boolean {
  return sharedLimit === null || selections.key_goals.length + selections.weak_areas.length < sharedLimit;
}

function canAddFocusValue(
  selections: FocusPresetSelections,
  group: PerformanceFocusGroup,
  limits: FocusPresetSelectionLimits,
): boolean {
  if (!hasSharedFocusSpace(selections, limits.sharedLimit)) return false;
  return group === "key_goals"
    ? selections.key_goals.length < limits.goalLimit
    : selections.weak_areas.length < limits.weakAreaLimit;
}

function focusValueAvailable(group: PerformanceFocusGroup, value: string, daysOutCtx: DaysOutContext): boolean {
  return getPerformanceFocusOptionAvailability(daysOutCtx, group, value).available;
}

export function resolveFocusPresetSelections(
  preset: FocusPreset,
  limits: FocusPresetSelectionLimits,
): FocusPresetSelections {
  const selections: FocusPresetSelections = {
    key_goals: [],
    weak_areas: [],
  };
  const rankCount = Math.max(preset.goals.length, preset.weak_areas.length);

  for (let rank = 0; rank < rankCount && hasSharedFocusSpace(selections, limits.sharedLimit); rank += 1) {
    const goal = preset.goals[rank];
    if (
      goal
      && canAddFocusValue(selections, "key_goals", limits)
      && focusValueAvailable("key_goals", goal, limits.daysOutCtx)
    ) {
      selections.key_goals.push(goal);
    }

    const weakArea = preset.weak_areas[rank];
    if (
      weakArea
      && canAddFocusValue(selections, "weak_areas", limits)
      && focusValueAvailable("weak_areas", weakArea, limits.daysOutCtx)
    ) {
      selections.weak_areas.push(weakArea);
    }
  }

  return selections;
}

export function matchesFocusPreset(
  keyGoals: string[],
  weakAreas: string[],
  limits: FocusPresetSelectionLimits,
): FocusPresetKey | null {
  for (const preset of FOCUS_PRESETS) {
    const selections = resolveFocusPresetSelections(preset, limits);
    if (
      sameStringSet(selections.key_goals, keyGoals)
      && sameStringSet(selections.weak_areas, weakAreas)
    ) {
      return preset.key;
    }
  }
  return null;
}

export type FocusPresetAvailability = {
  preset: FocusPreset;
  disabledReason: string | null;
};

export function getAvailableFocusPresets(input: {
  fightDate: string;
  noScheduledFight: boolean;
  limits: FocusPresetSelectionLimits;
}): FocusPresetAvailability[] {
  return FOCUS_PRESETS.map((preset) => {
    const selections = resolveFocusPresetSelections(preset, input.limits);
    return {
      preset,
      disabledReason: selections.key_goals.length === 0 ? "No goal available for this window." : null,
    };
  });
}

export type SetupSource = "preset" | "mixed" | "manual";

export function deriveSetupSource(matches: Array<string | null>): SetupSource {
  const total = matches.length;
  const hits = matches.filter((value) => value !== null).length;
  if (hits === 0) return "manual";
  if (hits === total) return "preset";
  return "mixed";
}

function assertValuesKnown(values: string[], options: IntakeOption[], label: string): void {
  const known = new Set(options.map((option) => option.value));
  for (const value of values) {
    if (!known.has(value)) {
      throw new Error(`recommended-setup: unknown ${label} value "${value}"`);
    }
  }
}

for (const preset of EQUIPMENT_PRESETS) {
  assertValuesKnown(preset.equipment_access, EQUIPMENT_ACCESS_OPTIONS, "equipment");
}
for (const preset of TRAINING_PRESETS) {
  assertValuesKnown(preset.training_availability, TRAINING_AVAILABILITY_OPTIONS, "training day");
  if (preset.weekly_training_frequency < 1 || preset.weekly_training_frequency > 6) {
    throw new Error(`recommended-setup: training preset "${preset.key}" frequency out of range`);
  }
  if (preset.weekly_training_frequency > preset.training_availability.length) {
    throw new Error(`recommended-setup: training preset "${preset.key}" frequency exceeds available days`);
  }
}
for (const preset of FOCUS_PRESETS) {
  assertValuesKnown(preset.goals, KEY_GOAL_OPTIONS, "key goal");
  assertValuesKnown(preset.weak_areas, WEAK_AREA_OPTIONS, "weak area");
  if (preset.goals.length < 1) {
    throw new Error(`recommended-setup: focus preset "${preset.key}" must have at least one goal`);
  }
}
