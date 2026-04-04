/**
 * Days-out policy loader for the frontend.
 *
 * Reads the shared `data/days_out_policy.json` (bundled at build time via
 * resolveJsonModule) so the intake UI can hide/disable/de-emphasize fields
 * without a network round-trip.
 *
 * This file mirrors the backend loader in `fightcamp/days_out_policy.py`.
 * The JSON file is the single source of truth.
 */

import policyData from "../../data/days_out_policy.json";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type InputRelevanceValue =
  | "required"
  | "used_if_present"
  | "advisory_only"
  | "ignore_for_planning"
  | "hide_or_disable_in_ui";

export type SparringDoseMode = "full" | "narrow" | "advisory" | "suppress";

export type PlannerPermissions = {
  allow_full_strength_block: boolean;
  allow_strength_anchor: boolean;
  allow_strength_primer_only: boolean;
  max_strength_exercises: number | null;
  allow_conditioning_build: boolean;
  allow_conditioning_reminder_only: boolean;
  allow_glycolytic: boolean;
  max_conditioning_stressors: number | null;
  allow_hard_sparring: boolean;
  allow_sparring_to_drive_architecture: boolean;
  max_hard_sparring_collision_owners: number | null;
  sparring_dose_mode: SparringDoseMode;
  allow_weekly_architecture: boolean;
  allow_weekly_frequency_to_influence_structure: boolean;
  allow_development_blocks: boolean;
  allow_multi_session_days: boolean;
  allow_accessory_volume: boolean;
  allow_novelty: boolean;
  freshness_priority: boolean;
  fight_day_protocol: boolean;
};

export type UIHints = {
  fight_proximity_banner: string | null;
  de_emphasize_fields: string[];
  disable_fields: string[];
  hide_fields: string[];
  helper_texts: Record<string, string>;
};

export type DaysOutContext = {
  daysOut: number | null;
  bucket: string;
  label: string;
  inputRelevance: Record<string, InputRelevanceValue>;
  plannerPermissions: PlannerPermissions;
  allowedSessionTypes: string[];
  forbiddenSessionTypes: string[];
  uiHints: UIHints;
  notes: string;
};

// ---------------------------------------------------------------------------
// Bucket resolution
// ---------------------------------------------------------------------------

type PolicyBucket = (typeof policyData.buckets)[keyof typeof policyData.buckets];

const buckets = policyData.buckets as Record<string, PolicyBucket>;

export function getDaysOutBucket(daysUntilFight: number | null | undefined): string {
  if (daysUntilFight == null || daysUntilFight > 7 || daysUntilFight < 0) {
    return "CAMP";
  }
  return `D-${daysUntilFight}`;
}

// ---------------------------------------------------------------------------
// Context builder
// ---------------------------------------------------------------------------

export function buildDaysOutContext(daysUntilFight: number | null | undefined): DaysOutContext {
  const bucket = getDaysOutBucket(daysUntilFight);
  const entry = buckets[bucket] ?? buckets["CAMP"];

  return {
    daysOut: daysUntilFight ?? null,
    bucket,
    label: entry.label ?? bucket,
    inputRelevance: (entry.input_relevance ?? {}) as Record<string, InputRelevanceValue>,
    plannerPermissions: (entry.planner_permissions ?? {}) as PlannerPermissions,
    allowedSessionTypes: entry.allowed_session_types ?? [],
    forbiddenSessionTypes: entry.forbidden_session_types ?? [],
    uiHints: {
      fight_proximity_banner: entry.ui_hints?.fight_proximity_banner ?? null,
      de_emphasize_fields: entry.ui_hints?.de_emphasize_fields ?? [],
      disable_fields: entry.ui_hints?.disable_fields ?? [],
      hide_fields: entry.ui_hints?.hide_fields ?? [],
      helper_texts: entry.ui_hints?.helper_texts ?? {},
    },
    notes: entry.notes ?? "",
  };
}

// ---------------------------------------------------------------------------
// Convenience helpers
// ---------------------------------------------------------------------------

export function fieldIgnored(ctx: DaysOutContext, fieldName: string): boolean {
  const rel = ctx.inputRelevance[fieldName];
  return rel === "ignore_for_planning" || rel === "hide_or_disable_in_ui";
}

export function fieldAdvisory(ctx: DaysOutContext, fieldName: string): boolean {
  return ctx.inputRelevance[fieldName] === "advisory_only";
}

export function fieldActive(ctx: DaysOutContext, fieldName: string): boolean {
  const rel = ctx.inputRelevance[fieldName];
  return rel === "required" || rel === "used_if_present";
}

export function shouldHideField(ctx: DaysOutContext, fieldName: string): boolean {
  return ctx.uiHints.hide_fields.includes(fieldName);
}

export function shouldDisableField(ctx: DaysOutContext, fieldName: string): boolean {
  return ctx.uiHints.disable_fields.includes(fieldName);
}

export function shouldDeEmphasizeField(ctx: DaysOutContext, fieldName: string): boolean {
  return ctx.uiHints.de_emphasize_fields.includes(fieldName);
}

export function getFieldHelperText(ctx: DaysOutContext, fieldName: string): string | undefined {
  return ctx.uiHints.helper_texts[fieldName];
}

/**
 * Compute days until fight from a date string (YYYY-MM-DD).
 * Returns null if the date cannot be parsed or is in the past.
 */
export function computeDaysUntilFight(fightDate: string | null | undefined): number | null {
  if (!fightDate) return null;
  const parsed = new Date(fightDate + "T00:00:00");
  if (isNaN(parsed.getTime())) return null;
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  const diffMs = parsed.getTime() - now.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  return diffDays < 0 ? null : diffDays;
}
