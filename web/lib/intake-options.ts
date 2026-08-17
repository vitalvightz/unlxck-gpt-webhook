export type IntakeOption = {
  label: string;
  value: string;
  disabled?: boolean;
};

export const GUIDED_INJURY_SEVERITY_VALUES = ["low", "moderate", "high"] as const;
export type GuidedInjurySeverity = (typeof GUIDED_INJURY_SEVERITY_VALUES)[number];

export const GUIDED_INJURY_SEVERITY_OPTIONS: IntakeOption[] = [
  { label: "Low", value: "low" },
  { label: "Moderate", value: "moderate" },
  { label: "High", value: "high" },
];

const GUIDED_INJURY_SEVERITY_ALIASES: Record<string, GuidedInjurySeverity> = {
  low: "low",
  mild: "low",
  moderate: "moderate",
  high: "high",
  severe: "high",
};

export function normalizeGuidedInjurySeverity(value: string | null | undefined): GuidedInjurySeverity | "" {
  const normalized = (value ?? "").trim().toLowerCase();
  return GUIDED_INJURY_SEVERITY_ALIASES[normalized] ?? "";
}

// Advances severity one step for the body-map tap-to-set interaction:
// unset/unknown → low → moderate → high → low. Always lands on a concrete
// severity so a marked zone is never left without a colour against the legend.
export function cycleGuidedInjurySeverity(value: string | null | undefined): GuidedInjurySeverity {
  const current = normalizeGuidedInjurySeverity(value);
  const index = current ? GUIDED_INJURY_SEVERITY_VALUES.indexOf(current) : -1;
  return GUIDED_INJURY_SEVERITY_VALUES[(index + 1) % GUIDED_INJURY_SEVERITY_VALUES.length];
}

export const TECHNICAL_STYLE_OPTIONS: IntakeOption[] = [
  { label: "Boxing", value: "boxing" },
  { label: "Kickboxing", value: "kickboxing" },
  { label: "Muay Thai", value: "muay_thai", disabled: true },
  { label: "MMA", value: "mma" },
  { label: "Wrestling", value: "wrestling", disabled: true },
  { label: "BJJ", value: "bjj", disabled: true },
];

export const TACTICAL_STYLE_OPTIONS: IntakeOption[] = [
  { label: "Pressure Fighter", value: "pressure_fighter" },
  { label: "Counter Striker", value: "counter_striker" },
  { label: "Distance Striker", value: "distance_striker" },
  { label: "Clinch Fighter", value: "clinch_fighter" },
  { label: "Grappler", value: "grappler" },
  { label: "Hybrid", value: "hybrid" },
];

export const PROFESSIONAL_STATUS_OPTIONS: IntakeOption[] = [
  { label: "Amateur", value: "amateur" },
  { label: "Professional", value: "professional" },
];

export const STANCE_OPTIONS: IntakeOption[] = [
  { label: "Orthodox", value: "Orthodox" },
  { label: "Southpaw", value: "Southpaw" },
  { label: "Switch", value: "Switch" },
  { label: "Hybrid", value: "Hybrid" },
];

export const TRAINING_AVAILABILITY_OPTIONS: IntakeOption[] = [
  { label: "Monday", value: "Monday" },
  { label: "Tuesday", value: "Tuesday" },
  { label: "Wednesday", value: "Wednesday" },
  { label: "Thursday", value: "Thursday" },
  { label: "Friday", value: "Friday" },
  { label: "Saturday", value: "Saturday" },
  { label: "Sunday", value: "Sunday" },
];

export type EquipmentAccessGroup = {
  label: string;
  options: IntakeOption[];
};

// This grouped list is the intake source of truth. Keep the persisted values
// stable: plans, drafts and previously completed intakes store these values.
export const EQUIPMENT_ACCESS_GROUPS: EquipmentAccessGroup[] = [
  {
    label: "Free weights",
    options: [
      { label: "Dumbbells", value: "dumbbells" },
      { label: "Kettlebells", value: "kettlebells" },
      { label: "Medicine Ball", value: "medicine_ball" },
      { label: "Sandbag", value: "sandbag" },
      { label: "Bulgarian Bag", value: "bulgarian_bag" },
      { label: "Atlas Stones", value: "atlas_stone" },
      { label: "Plates", value: "plate" },
      { label: "Water Jug", value: "water_jug" },
    ],
  },
  {
    label: "Bars & strength stations",
    options: [
      { label: "Barbell", value: "barbell" },
      { label: "Trap Bar", value: "trap_bar" },
      { label: "Pull-Up Bar", value: "pullup_bar" },
      { label: "Cable", value: "cable" },
      { label: "Landmine", value: "landmine" },
      { label: "Bench", value: "bench" },
      { label: "Log", value: "log" },
    ],
  },
  {
    label: "Conditioning machines",
    options: [
      { label: "Assault Bike", value: "assault_bike" },
      { label: "Rower", value: "rower" },
      { label: "Pool", value: "pool" },
      { label: "Step Mill", value: "step_mill" },
      { label: "Treadmill", value: "treadmill" },
    ],
  },
  {
    label: "Combat training",
    options: [
      { label: "Heavy Bag", value: "heavy_bag" },
      { label: "Thai Pads", value: "thai_pads" },
      { label: "Partner", value: "partner" },
    ],
  },
  {
    label: "Plyometrics & agility",
    options: [
      { label: "Plyo Box / Box", value: "box" },
      { label: "Agility Ladder", value: "agility_ladder" },
      { label: "Jump Rope", value: "jump_rope" },
      { label: "Hurdles", value: "hurdles" },
    ],
  },
  {
    label: "Functional conditioning",
    options: [
      { label: "Sled", value: "sled" },
      { label: "Battle Ropes", value: "battle_ropes" },
      { label: "Sledgehammer", value: "sledgehammer" },
      { label: "Tire", value: "tire" },
      { label: "Weight Vest", value: "weight_vest" },
    ],
  },
  {
    label: "Accessories & recovery",
    options: [
      { label: "Bands", value: "bands" },
      { label: "Bosu Ball", value: "bosu_ball" },
      { label: "Foam Roller", value: "foam_roller" },
      { label: "Neck Harness", value: "neck_harness" },
      { label: "Swiss Ball", value: "swiss_ball" },
      { label: "Towel", value: "towel" },
      { label: "TRX", value: "trx" },
      { label: "Weight Belt", value: "weight_belt" },
    ],
  },
];

export const EQUIPMENT_ACCESS_OPTIONS: IntakeOption[] = EQUIPMENT_ACCESS_GROUPS.flatMap(
  (group) => group.options,
);

export const KEY_GOAL_OPTIONS: IntakeOption[] = [
  { label: "Power", value: "power" },
  { label: "Strength", value: "strength" },
  { label: "Conditioning", value: "conditioning" },
  { label: "Speed", value: "speed" },
  { label: "Skill Refinement", value: "skill_refinement" },
  { label: "Mobility", value: "mobility" },
  { label: "Recovery", value: "recovery" },
  { label: "Weight Cut Support", value: "weight_cut" },
];

export const WEAK_AREA_OPTIONS: IntakeOption[] = [
  { label: "Gas Tank", value: "gas_tank" },
  { label: "Strength", value: "strength" },
  { label: "Power", value: "power" },
  { label: "Speed", value: "speed" },
  { label: "Footwork", value: "footwork" },
  { label: "Balance", value: "balance" },
  { label: "Mobility", value: "mobility" },
  { label: "Coordination", value: "coordination" },
  { label: "Core / Trunk Strength", value: "trunk_strength" },
];

export const RECORD_PATTERN = /^\d+-\d+(?:-\d+)?$/;

const LEGACY_OPTION_LABELS: Record<string, string> = {
  air_bike: "Air Bike",
  dumbbell: "Dumbbell",
  kettlebell: "Kettlebell",
  jump_rope: "Jump Rope",
};

export function detectDeviceTimeZone(): string {
  if (typeof window === "undefined" || typeof Intl === "undefined") {
    return "";
  }
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
}

export function detectDeviceLocale(): string {
  if (typeof navigator === "undefined") {
    return "";
  }
  return navigator.language || "";
}

export function sanitizeRecordInput(value: string): string {
  return value.replace(/[^\d-]/g, "").replace(/-{2,}/g, "-");
}

export function isValidRecordFormat(value: string): boolean {
  const normalized = value.trim();
  return !normalized || RECORD_PATTERN.test(normalized);
}

export function toggleListValue(values: string[], target: string): string[] {
  return values.includes(target)
    ? values.filter((value) => value !== target)
    : [...values, target];
}

export function retainKnownOptionValues(values: string[] | undefined, options: IntakeOption[]): string[] {
  const knownValues = new Set(options.filter((option) => !option.disabled).map((option) => option.value));
  return (values ?? []).filter((value) => knownValues.has(value));
}

export function getOptionLabel(options: IntakeOption[], value: string): string {
  return options.find((option) => option.value === value)?.label ?? LEGACY_OPTION_LABELS[value] ?? value;
}

export function getOptionLabels(options: IntakeOption[], values: string[] | undefined): string[] {
  return (values ?? []).map((value) => getOptionLabel(options, value));
}
