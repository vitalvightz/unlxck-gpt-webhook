import {
  EQUIPMENT_ACCESS_OPTIONS,
  KEY_GOAL_OPTIONS,
  TRAINING_AVAILABILITY_OPTIONS,
  WEAK_AREA_OPTIONS,
  type IntakeOption,
} from "@/lib/intake-options";
import { getPerformanceFocusCap } from "@/lib/performance-focus-cap";

export type EquipmentPresetKey = "home" | "basic_gym" | "full_gym";
export type TrainingPresetKey = "three_days" | "four_days" | "five_days";
export type FocusPresetKey =
  | "explosive_power"
  | "gas_tank"
  | "strength_base"
  | "mobility_recovery"
  | "fight_sharpness";

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
  key_goals: string[];
  weak_areas: string[];
  allowNoScheduledFight: boolean;
  // Boundaries on daysUntilFight. Inclusive on both sides. `null` = unbounded.
  minDaysUntilFight: number | null;
  maxDaysUntilFight: number | null;
};

export const EQUIPMENT_PRESETS: EquipmentPreset[] = [
  {
    key: "home",
    label: "Home & bodyweight",
    description: "Bands, bag, partner",
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

// Fight-window thresholds align with the performance-focus-cap window boundaries (7/21/42 days)
// so the same fight-camp mental model drives both filtering and cap counting.
export const FOCUS_PRESETS: FocusPreset[] = [
  {
    key: "strength_base",
    label: "Strength base",
    description: "Strength · Strength weakness",
    key_goals: ["strength"],
    weak_areas: ["strength"],
    allowNoScheduledFight: true,
    minDaysUntilFight: 43,
    maxDaysUntilFight: null,
  },
  {
    key: "explosive_power",
    label: "Explosive power",
    description: "Power · Power weakness",
    key_goals: ["power"],
    weak_areas: ["power"],
    allowNoScheduledFight: true,
    minDaysUntilFight: 21,
    maxDaysUntilFight: null,
  },
  {
    key: "gas_tank",
    label: "Gas tank",
    description: "Conditioning · Gas tank weakness",
    key_goals: ["conditioning"],
    weak_areas: ["gas_tank"],
    allowNoScheduledFight: true,
    minDaysUntilFight: 21,
    maxDaysUntilFight: null,
  },
  {
    key: "fight_sharpness",
    label: "Fight sharpness",
    description: "Speed · Speed weakness",
    key_goals: ["speed"],
    weak_areas: ["speed"],
    allowNoScheduledFight: false,
    minDaysUntilFight: 0,
    maxDaysUntilFight: 42,
  },
  {
    key: "mobility_recovery",
    label: "Mobility & recovery",
    description: "Recovery · Mobility focus",
    // For injury accommodation, the planner reads the Injuries field — this preset
    // only nudges goal emphasis. Naming intentionally avoids any "injury-safe" claim.
    key_goals: ["recovery", "mobility"],
    weak_areas: [],
    allowNoScheduledFight: true,
    minDaysUntilFight: null,
    maxDaysUntilFight: null,
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
    description: "Mon, Tue, Wed, Thu, Sat",
    training_availability: ["Monday", "Tuesday", "Wednesday", "Thursday", "Saturday"],
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

export function matchesFocusPreset(
  keyGoals: string[],
  weakAreas: string[],
): FocusPresetKey | null {
  for (const preset of FOCUS_PRESETS) {
    if (
      sameStringSet(preset.key_goals, keyGoals)
      && sameStringSet(preset.weak_areas, weakAreas)
    ) {
      return preset.key;
    }
  }
  return null;
}

export type FocusPresetAvailability = {
  preset: FocusPreset;
  // If non-null, the preset is shown but disabled, with this string as the reason.
  // Presets that don't fit the fight window are filtered out entirely instead.
  disabledReason: string | null;
};

export function getAvailableFocusPresets(input: {
  fightDate: string;
  noScheduledFight: boolean;
  now?: Date;
  timeZone?: string | null;
}): FocusPresetAvailability[] {
  const cap = !input.noScheduledFight && input.fightDate
    ? getPerformanceFocusCap(input.fightDate, { now: input.now, timeZone: input.timeZone })
    : null;
  const daysUntilFight = cap?.daysUntilFight ?? null;
  const isOpenCamp = input.noScheduledFight || daysUntilFight === null;

  return FOCUS_PRESETS.flatMap((preset) => {
    if (isOpenCamp) {
      if (!preset.allowNoScheduledFight) return [];
    } else {
      if (preset.minDaysUntilFight !== null && (daysUntilFight ?? 0) < preset.minDaysUntilFight) return [];
      if (preset.maxDaysUntilFight !== null && (daysUntilFight ?? 0) > preset.maxDaysUntilFight) return [];
    }

    // Defensive cap check. With current preset shapes (≤2 selections) and minimum cap 2,
    // this branch should not trigger — but we keep it so a future cap rule change can't
    // silently produce a preset that exceeds it.
    let disabledReason: string | null = null;
    if (cap) {
      const totalSelections = preset.key_goals.length + preset.weak_areas.length;
      if (totalSelections > cap.maxSelections) {
        disabledReason = "Too broad for this fight window.";
      }
    }

    return [{ preset, disabledReason }];
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

// Module-load invariants. Catch typos at import time rather than letting `retainKnownOptionValues`
// silently drop them and produce an empty selection downstream.
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
  assertValuesKnown(preset.key_goals, KEY_GOAL_OPTIONS, "key goal");
  assertValuesKnown(preset.weak_areas, WEAK_AREA_OPTIONS, "weak area");
  const totalSelections = preset.key_goals.length + preset.weak_areas.length;
  if (totalSelections < 1) {
    throw new Error(`recommended-setup: focus preset "${preset.key}" must have at least one selection`);
  }
}
