import type { MeResponse, PlanRequest } from "@/lib/types";

import { detectDeviceTimeZone } from "@/lib/intake-options";

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
    weak_areas: [],
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
  const draft = (me.profile.onboarding_draft as PlanRequest | null | undefined) ?? base;
  const normalizedDraft = draft
    ? {
        ...draft,
        support_work_days: draft.support_work_days ?? (draft as PlanRequest & { technical_skill_days?: string[] }).technical_skill_days ?? [],
      }
    : fallback;

  return {
    ...fallback,
    ...normalizedDraft,
    athlete: {
      ...fallback.athlete,
      ...normalizedDraft.athlete,
      full_name: normalizedDraft.athlete?.full_name || me.profile.full_name,
      sex: normalizedDraft.athlete?.sex ?? me.profile.nutrition_profile?.sex ?? fallback.athlete.sex,
      age: normalizedDraft.athlete?.age ?? me.profile.nutrition_profile?.age ?? fallback.athlete.age,
      height_cm: normalizedDraft.athlete?.height_cm ?? me.profile.nutrition_profile?.height_cm ?? fallback.athlete.height_cm,
      technical_style: normalizedDraft.athlete?.technical_style ?? me.profile.technical_style ?? [],
      tactical_style: normalizedDraft.athlete?.tactical_style ?? me.profile.tactical_style ?? [],
      stance: normalizedDraft.athlete?.stance ?? me.profile.stance ?? "",
      professional_status:
        normalizedDraft.athlete?.professional_status ?? me.profile.professional_status ?? "",
      record: normalizedDraft.athlete?.record ?? me.profile.record ?? "",
      athlete_timezone:
        normalizedDraft.athlete?.athlete_timezone ?? me.profile.athlete_timezone ?? fallback.athlete.athlete_timezone,
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
