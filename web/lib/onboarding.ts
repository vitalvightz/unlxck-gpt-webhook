import type { MeResponse, PlanRequest } from "@/lib/types";

import { detectDeviceTimeZone } from "@/lib/intake-options";

function isEmptyValue(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (typeof value === "string") return value.trim() === "";
  if (Array.isArray(value)) return value.length === 0;
  return false;
}

type DraftWithSource = PlanRequest & { plan_source?: string };

function isQuickBuildDraft(draft: PlanRequest | null): draft is DraftWithSource {
  return (draft as DraftWithSource | null)?.plan_source === "quick_build";
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
  if (top.no_scheduled_fight === true) {
    merged.fight_date = "";
    merged.no_scheduled_fight = true;
  }
  return merged as PlanRequest;
}

export function applyNoScheduledFightSnapshot(form: PlanRequest, noScheduledFight: boolean): PlanRequest {
  if (!noScheduledFight) {
    return {
      ...form,
      no_scheduled_fight: false,
    };
  }
  return {
    ...form,
    no_scheduled_fight: true,
    fight_date: "",
  };
}

function mergeAthleteLayers(
  base: PlanRequest["athlete"],
  top?: Partial<PlanRequest["athlete"]> | null,
): PlanRequest["athlete"] {
  if (!top) return base;
  const merged: Record<string, unknown> = { ...base };
  for (const key of Object.keys(top) as (keyof PlanRequest["athlete"])[]) {
    const topValue = top[key];
    merged[key] = isEmptyValue(topValue) ? base[key] : topValue;
  }
  return merged as PlanRequest["athlete"];
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
    fatigue_level: "low",
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
  const layered = normalizedDraft
    ? (isQuickBuildDraft(normalizedDraft) ? normalizedDraft : mergeIntakeLayers(base, normalizedDraft))
    : base;

  // Layer order for athlete fields: defaults < profile-derived < latest_intake.athlete < draft.athlete.
  // Each layer only overrides when its value is non-empty, so a partial draft (e.g. record: "",
  // technical_style: []) never clobbers prior values pulled from the previous intake or the profile.
  const profileAthlete: Partial<PlanRequest["athlete"]> = {
    full_name: me.profile.full_name,
    sex: me.profile.nutrition_profile?.sex ?? null,
    age: me.profile.nutrition_profile?.age ?? null,
    height_cm: me.profile.nutrition_profile?.height_cm ?? null,
    technical_style: me.profile.technical_style,
    tactical_style: me.profile.tactical_style,
    stance: me.profile.stance,
    professional_status: me.profile.professional_status,
    record: me.profile.record,
    athlete_timezone: me.profile.athlete_timezone,
  };

  const withProfile = mergeAthleteLayers(fallback.athlete, profileAthlete);
  const withIntake = mergeAthleteLayers(withProfile, base.athlete);
  const finalAthlete = mergeAthleteLayers(withIntake, normalizedDraft?.athlete);

  return {
    ...fallback,
    ...layered,
    athlete: finalAthlete,
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
