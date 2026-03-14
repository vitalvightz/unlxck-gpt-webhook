export type IntakeOption = {
  label: string;
  value: string;
};

export const TECHNICAL_STYLE_OPTIONS: IntakeOption[] = [
  { label: "Boxing", value: "boxing" },
  { label: "Kickboxing", value: "kickboxing" },
  { label: "Muay Thai", value: "muay_thai" },
  { label: "MMA", value: "mma" },
  { label: "Wrestling", value: "wrestling" },
  { label: "BJJ", value: "bjj" },
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

export const EQUIPMENT_ACCESS_OPTIONS: IntakeOption[] = [
  { label: "Bodyweight", value: "bodyweight" },
  { label: "Dumbbells", value: "dumbbells" },
  { label: "Kettlebells", value: "kettlebells" },
  { label: "Barbell", value: "barbell" },
  { label: "Trap Bar", value: "trap_bar" },
  { label: "Pull-Up Bar", value: "pullup_bar" },
  { label: "Sled", value: "sled" },
  { label: "Medicine Ball", value: "medicine_ball" },
  { label: "Bands", value: "bands" },
  { label: "Cable", value: "cable" },
  { label: "Landmine", value: "landmine" },
  { label: "Heavy Bag", value: "heavy_bag" },
  { label: "Thai Pads", value: "thai_pads" },
  { label: "Assault Bike", value: "assault_bike" },
  { label: "Rower", value: "rower" },
  { label: "Partner", value: "partner" },
];

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
  { label: "Trunk Strength", value: "trunk_strength" },
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
  const knownValues = new Set(options.map((option) => option.value));
  return (values ?? []).filter((value) => knownValues.has(value));
}

export function getOptionLabel(options: IntakeOption[], value: string): string {
  return options.find((option) => option.value === value)?.label ?? LEGACY_OPTION_LABELS[value] ?? value;
}

export function getOptionLabels(options: IntakeOption[], values: string[] | undefined): string[] {
  return (values ?? []).map((value) => getOptionLabel(options, value));
}
