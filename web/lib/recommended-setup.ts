import {
  EQUIPMENT_ACCESS_OPTIONS,
  TRAINING_AVAILABILITY_OPTIONS,
  type IntakeOption,
} from "@/lib/intake-options";

export type EquipmentPresetKey = "home" | "basic_gym" | "full_gym";
export type TrainingPresetKey = "three_days" | "four_days" | "five_days";

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

export const EQUIPMENT_PRESETS: EquipmentPreset[] = [
  {
    key: "home",
    label: "Home / bodyweight",
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
