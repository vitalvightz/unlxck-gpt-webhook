const LABEL_OVERRIDES: Record<string, string> = {
  train_as_planned: "Train as planned",
  modify: "Modify",
  pull_back: "Pull back",
  unavailable: "Unavailable",
  stop_and_report: "Stop and report",

  publishable_with_flags: "Ready",
  ready: "Ready",

  gpp: "General prep",
  spp: "Specific prep",
  taper: "Fight week taper",
  fight_week: "Fight week",
  reintegration: "Reintegration",

  strength_power: "Strength & power",
  conditioning: "Conditioning",
  skill: "Skill",
  sparring: "Sparring",
  recovery: "Recovery",
  mixed: "Mixed session",
  primer: "Primer",
  fight_or_match: "Fight day",

  preparation: "Preparation",
  mobility_activation: "Mobility",
  plyometric_power: "Power",
  strength: "Strength",
  accessory: "Accessory",
  cooldown_recovery: "Cooldown",

  red: "Red",
  amber: "Amber",
  green: "Green",

  morning_check_in: "Morning check-in",
};

function normalizeToken(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[\s\-/]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "");
}

function titleizeLabel(value: string): string {
  return value
    .replace(/[_\-/]+/g, " ")
    .trim()
    .replace(/\s+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function formatPlanLabel(value: unknown): string {
  if (typeof value !== "string") {
    return "";
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return "";
  }
  const override = LABEL_OVERRIDES[normalizeToken(trimmed)];
  return override ?? titleizeLabel(trimmed);
}

export function isRawEnumLabel(value: unknown): boolean {
  if (typeof value !== "string") {
    return false;
  }
  const trimmed = value.trim();
  if (!trimmed || /\s/.test(trimmed)) {
    return false;
  }
  if (/^[A-Z][a-z]+$/.test(trimmed)) {
    return false;
  }
  return /^[a-z0-9]+(_[a-z0-9]+)*$/i.test(trimmed);
}

/**
 * Humanize a value only when it looks like a raw backend enum (a single
 * snake/kebab token). Already-human strings like "High pain" are returned
 * untouched so we never re-titlecase prose. Safe to apply defensively at render
 * sites where a field might be either human copy or a leaked enum.
 */
export function humanizeIfRawEnum(value: unknown): string {
  if (typeof value !== "string") {
    return "";
  }
  return isRawEnumLabel(value) ? formatPlanLabel(value) : value;
}
