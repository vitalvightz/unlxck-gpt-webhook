// Human-readable UI labels for the structured plan.
//
// The backend stores machine enums (e.g. "train_as_planned", "SPP",
// "MOBILITY ACTIVATION") and PR-9 turns the renderer into a command screen
// rather than a raw debug view. This module is the single, pure, testable place
// that maps a raw value to its athlete-facing label. It NEVER mutates stored
// values — it only formats for display.

// Overrides keyed by a normalized token (lowercase, separators collapsed to a
// single underscore). Anything not listed falls back to a generic titleizer.
const LABEL_OVERRIDES: Record<string, string> = {
  // Readiness / daily-check-in decisions
  train_as_planned: "Train as planned",
  modify: "Modify",
  pull_back: "Pull back",
  unavailable: "Unavailable",
  stop_and_report: "Stop and report",

  // Plan / publish status
  publishable_with_flags: "Ready with notes",
  ready: "Ready",

  // Phase labels
  gpp: "General prep",
  spp: "Specific prep",
  taper: "Fight week taper",
  fight_week: "Fight week",
  reintegration: "Reintegration",

  // Session types
  strength_power: "Strength & power",
  conditioning: "Conditioning",
  skill: "Skill",
  sparring: "Sparring",
  recovery: "Recovery",
  mixed: "Mixed session",
  primer: "Primer",
  fight_or_match: "Fight day",

  // Block types
  preparation: "Preparation",
  mobility_activation: "Mobility",
  plyometric_power: "Power",
  strength: "Strength",
  accessory: "Accessory",
  cooldown_recovery: "Cooldown",

  // Severities
  red: "Red",
  amber: "Amber",
  green: "Green",

  // Red-flag timing
  morning_check_in: "Morning check-in",
};

/** Normalize a raw value to the override key: lowercase, separators → "_". */
function normalizeToken(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[\s\-/]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "");
}

/** Generic fallback: "mobility_activation" / "FIGHT OR MATCH" → "Mobility Activation". */
function titleizeLabel(value: string): string {
  return value
    .replace(/[_\-/]+/g, " ")
    .trim()
    .replace(/\s+/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

/**
 * The athlete-facing label for a raw enum/machine value.
 *
 * Returns a curated override when one exists, otherwise a generic titleized
 * form. Empty/blank input returns "". Display-only — never changes stored data.
 */
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

/**
 * Whether a string looks like a raw machine enum (snake_case token, no spaces),
 * e.g. "stop_and_report". Used to hide duplicated raw action enums in the UI
 * when a human-readable display text is already shown.
 */
export function isRawEnumLabel(value: unknown): boolean {
  if (typeof value !== "string") {
    return false;
  }
  const trimmed = value.trim();
  if (!trimmed || /\s/.test(trimmed)) {
    return false;
  }
  // A single token (optionally snake_cased) with no spaces — the shape
  // backend enums take. "Stop and report." (a sentence) is not raw.
  return /^[a-z0-9]+(_[a-z0-9]+)*$/i.test(trimmed);
}
