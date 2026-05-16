import type { MeResponse, PlanRequest } from "@/lib/types";

import { detectDeviceTimeZone } from "@/lib/intake-options";

function isEmptyValue(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (typeof value === "string") return value.trim() === "";
  if (Array.isArray(value)) return value.length === 0;
  return false;
}

// Layer `top` on `base` field-by-field, preferring `top` only when it carries a non-empty value.
// Lets a partial onboarding_draft pull untouched fields from latest_intake instead of clobbering them.
function mergeIntakeLayers(base: PlanRequest, top: PlanRequest): PlanRequest {
  const merged: Record<string, unknown> = { ...base };
  for (const key of Object.keys(top) as (keyof PlanRequest)[]) {
    if (key === "athlete") continue;
    const topValue = top[key];
    merged[key] = isEmptyValue(topValue) ? base[key] : topValue;
  }
  return merged as PlanRequest;
}

export function emptyPlanRequest(fullName = ""): PlanRequest {
  return {
    athlete: {
      full_name: fullName,
      sex: null,
      age: null,
      weight_kg: null,
      target_weight_kg: null,
      height_cm: null,
      technical_style: [],
      tactical_style: [],
      stance: "",
      professional_status: "",
      record: "",
      athlete_timezone: detectDeviceTimeZone(),
      athlete_locale: "",
    },
    fight_date: "",
    no_scheduled_fight: false,
    rounds_format: "3 x 3",
    weekly_training_frequency: 4,
    fatigue_level: "moderate",
    equipment_access: [],
    training_availability: [],
    hard_sparring_days: [],
    support_work_days: [],
    injuries: "",
    guided_injury: null,
    guided_injuries: [],
    key_goals: [],
    primary_goal: "",
    weak_areas: [],
    primary_weak_area: "",
    goal_weakness_collision_detail: "",
    goal_weakness_collision_tags: [],
    goal_weakness_collision_details: [],
    training_preference: "",
    mindset_challenges: "",
    notes: "",
  };
}

export function hydratePlanRequest(me: MeResponse | null): PlanRequest {
  const fallback = emptyPlanRequest(me?.profile.full_name ?? "");
  if (!me) {
    return fallback;
  }

  const base = me.latest_intake ?? fallback;
  const draftSource = (me.profile.onboarding_draft as PlanRequest | null | undefined) ?? null;
  const normalizedDraft = draftSource
    ? {
        ...draftSource,
        support_work_days: draftSource.support_work_days ?? (draftSource as PlanRequest & { technical_skill_days?: string[] }).technical_skill_days ?? [],
      }
    : null;

  // Layer order: defaults < latest_intake < onboarding_draft (non-empty wins).
  // A partially-completed draft still pulls untouched fields from the last completed intake.
  const layered = normalizedDraft ? mergeIntakeLayers(base, normalizedDraft) : base;

  const draftAthlete = normalizedDraft?.athlete;
  const intakeAthlete = base.athlete;

  return {
    ...fallback,
    ...layered,
    athlete: {
      ...fallback.athlete,
      ...intakeAthlete,
      ...(draftAthlete ?? {}),
      full_name: draftAthlete?.full_name || intakeAthlete?.full_name || me.profile.full_name,
      sex: draftAthlete?.sex ?? intakeAthlete?.sex ?? me.profile.nutrition_profile?.sex ?? fallback.athlete.sex,
      age: draftAthlete?.age ?? intakeAthlete?.age ?? me.profile.nutrition_profile?.age ?? fallback.athlete.age,
      height_cm: draftAthlete?.height_cm ?? intakeAthlete?.height_cm ?? me.profile.nutrition_profile?.height_cm ?? fallback.athlete.height_cm,
      technical_style: draftAthlete?.technical_style ?? intakeAthlete?.technical_style ?? me.profile.technical_style ?? [],
      tactical_style: draftAthlete?.tactical_style ?? intakeAthlete?.tactical_style ?? me.profile.tactical_style ?? [],
      stance: draftAthlete?.stance ?? intakeAthlete?.stance ?? me.profile.stance ?? "",
      professional_status:
        draftAthlete?.professional_status ?? intakeAthlete?.professional_status ?? me.profile.professional_status ?? "",
      record: draftAthlete?.record ?? intakeAthlete?.record ?? me.profile.record ?? "",
      athlete_timezone:
        draftAthlete?.athlete_timezone ?? intakeAthlete?.athlete_timezone ?? me.profile.athlete_timezone ?? fallback.athlete.athlete_timezone,
    },
  };
}

export function mergePlanRequestDraft(
  existingDraft: Record<string, unknown> | null | undefined,
  nextPlanRequest: PlanRequest,
  currentStep: number,
): Record<string, unknown> {
  return {
    ...(existingDraft ?? {}),
    ...nextPlanRequest,
    current_step: currentStep,
  };
}

export function csvToList(value: string): string[] {
  return value
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

export function listToCsv(values: string[] | undefined): string {
  return (values ?? []).join(", ");
}
