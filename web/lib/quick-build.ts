import {
  detectDeviceTimeZone,
  EQUIPMENT_ACCESS_OPTIONS,
  KEY_GOAL_OPTIONS,
  TACTICAL_STYLE_OPTIONS,
  TECHNICAL_STYLE_OPTIONS,
  TRAINING_AVAILABILITY_OPTIONS,
  WEAK_AREA_OPTIONS,
  retainKnownOptionValues,
} from "@/lib/intake-options";
import { applyNoScheduledFightSnapshot, canonicalizePerformanceFocus, emptyPlanRequest } from "@/lib/onboarding";
import {
  buildDaysOutContext,
  computeDaysUntilFight,
  filterAvailablePerformanceFocusValues,
} from "@/lib/days-out-policy";
import { validatePerformanceFocusSelections } from "@/lib/performance-focus-cap";
import { HARD_SPARRING_DAY_CAP } from "@/lib/training-schedule";
import { buildAthleteInjuryTexts } from "@/lib/guided-injury";
import type { PlanRequest } from "@/lib/types";

export const QUICK_BUILD_KEY_GOAL_CAP = 3;
export const QUICK_BUILD_WEAK_AREA_CAP = 2;
const ROUNDS_FORMAT_PATTERN = /^\d+\s*[xX]\s*\d+$/;
const FIGHT_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

export type QuickBuildInput = {
  full_name: string;
  technical_style: string[];
  tactical_style: string[];
  fight_date: string;
  no_scheduled_fight: boolean;
  rounds_format: string;
  weekly_training_frequency: number;
  training_availability: string[];
  hard_sparring_days: string[];
  equipment_access: string[];
  key_goals: string[];
  weak_areas: string[];
  injuries: string;
};

export function emptyQuickBuildInput(fullName = ""): QuickBuildInput {
  return {
    full_name: fullName,
    technical_style: [],
    tactical_style: [],
    fight_date: "",
    no_scheduled_fight: false,
    rounds_format: "3 x 3",
    weekly_training_frequency: 4,
    training_availability: [],
    hard_sparring_days: [],
    equipment_access: [],
    key_goals: [],
    weak_areas: [],
    injuries: "",
  };
}

export function planRequestToQuickBuildInput(plan: PlanRequest): QuickBuildInput {
  const trainingAvailability = retainKnownOptionValues(
    plan.training_availability ?? [],
    TRAINING_AVAILABILITY_OPTIONS,
  );
  const weeklyFrequencyRaw = plan.weekly_training_frequency ?? 4;
  const weeklyFrequency = Math.min(
    Math.max(Number.isFinite(weeklyFrequencyRaw) ? weeklyFrequencyRaw : 4, 1),
    6,
  );
  return {
    full_name: plan.athlete?.full_name ?? "",
    technical_style: retainKnownOptionValues(
      plan.athlete?.technical_style ?? [],
      TECHNICAL_STYLE_OPTIONS,
    ).slice(0, 1),
    tactical_style: retainKnownOptionValues(
      plan.athlete?.tactical_style ?? [],
      TACTICAL_STYLE_OPTIONS,
    ).slice(0, 1),
    fight_date: plan.no_scheduled_fight ? "" : (plan.fight_date ?? ""),
    no_scheduled_fight: Boolean(plan.no_scheduled_fight),
    rounds_format: plan.rounds_format || "3 x 3",
    weekly_training_frequency: weeklyFrequency,
    training_availability: trainingAvailability,
    hard_sparring_days: retainKnownOptionValues(
      plan.hard_sparring_days ?? [],
      TRAINING_AVAILABILITY_OPTIONS,
    )
      .filter((day) => trainingAvailability.includes(day))
      .slice(0, HARD_SPARRING_DAY_CAP),
    equipment_access: retainKnownOptionValues(
      plan.equipment_access ?? [],
      EQUIPMENT_ACCESS_OPTIONS,
    ),
    key_goals: retainKnownOptionValues(plan.key_goals ?? [], KEY_GOAL_OPTIONS).slice(
      0,
      QUICK_BUILD_KEY_GOAL_CAP,
    ),
    weak_areas: retainKnownOptionValues(plan.weak_areas ?? [], WEAK_AREA_OPTIONS).slice(
      0,
      QUICK_BUILD_WEAK_AREA_CAP,
    ),
    // When the athlete completed the advanced intake, plan.injuries holds the
    // planner's structured comprehension ("Left shoulder is bruised (low,
    // stable). Type: surface_injury. Surface: bruise..."), not their own words.
    // Show what they actually typed; fall back to the free-text field only when
    // there are no structured guided injuries to draw from.
    injuries: buildAthleteInjuryTexts(plan.guided_injuries) || (plan.injuries ?? "").trim(),
  };
}

function isFutureOrToday(value: string, now: Date = new Date()): boolean {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return false;
  const [, y, m, d] = match;
  const fightUtc = Date.UTC(Number(y), Number(m) - 1, Number(d));
  const todayUtc = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  return Number.isFinite(fightUtc) && fightUtc >= todayUtc;
}

export type QuickBuildValidationErrors = Partial<Record<keyof QuickBuildInput | "focus_cap", string>>;

export function sanitizeQuickBuildFocusByDaysOut(input: QuickBuildInput, now?: Date): Pick<QuickBuildInput, "key_goals" | "weak_areas"> {
  const daysUntilFight = input.no_scheduled_fight ? null : computeDaysUntilFight(input.fight_date, now);
  const daysOutCtx = buildDaysOutContext(daysUntilFight);
  return {
    key_goals: filterAvailablePerformanceFocusValues(daysOutCtx, "key_goals", input.key_goals),
    weak_areas: filterAvailablePerformanceFocusValues(daysOutCtx, "weak_areas", input.weak_areas),
  };
}

export function validateQuickBuildInput(
  input: QuickBuildInput,
  options?: { now?: Date; timeZone?: string | null },
): QuickBuildValidationErrors {
  const errors: QuickBuildValidationErrors = {};

  if (!input.full_name.trim()) {
    errors.full_name = "Add your full name.";
  }
  if (input.technical_style.length === 0) {
    errors.technical_style = "Choose a style.";
  } else if (input.technical_style.length > 1) {
    errors.technical_style = "Pick only one technical style.";
  }
  if (input.tactical_style.length > 1) {
    errors.tactical_style = "Pick only one tactical style.";
  }
  if (input.no_scheduled_fight) {
    if (input.fight_date) {
      errors.fight_date = "Clear the fight date or turn off \"no scheduled fight\".";
    }
  } else {
    if (!input.fight_date) {
      errors.fight_date = "Add a fight date or choose open camp.";
    } else if (!FIGHT_DATE_PATTERN.test(input.fight_date)) {
      errors.fight_date = "Fight date must be in YYYY-MM-DD format.";
    } else if (!isFutureOrToday(input.fight_date, options?.now)) {
      errors.fight_date = "Fight date cannot be in the past.";
    }
  }
  if (!ROUNDS_FORMAT_PATTERN.test(input.rounds_format)) {
    errors.rounds_format = "Pick a rounds format.";
  }
  if (!Number.isInteger(input.weekly_training_frequency) || input.weekly_training_frequency < 1 || input.weekly_training_frequency > 6) {
    errors.weekly_training_frequency = "Sessions per week must be between 1 and 6.";
  }
  if (input.training_availability.length === 0) {
    errors.training_availability = "Choose at least one training day.";
  } else if (input.weekly_training_frequency > input.training_availability.length) {
    errors.training_availability = "Sessions per week cannot exceed selected training days.";
  }
  if (input.hard_sparring_days.length > 0) {
    const availabilitySet = new Set(input.training_availability);
    if (input.hard_sparring_days.some((day) => !availabilitySet.has(day))) {
      errors.hard_sparring_days = "Hard sparring days must be inside your training days.";
    } else if (input.hard_sparring_days.length > HARD_SPARRING_DAY_CAP) {
      errors.hard_sparring_days = `Pick at most ${HARD_SPARRING_DAY_CAP} hard sparring days.`;
    }
  }
  if (input.equipment_access.length === 0) {
    errors.equipment_access = "Choose your equipment.";
  }
  if (input.key_goals.length === 0) {
    errors.key_goals = "Choose at least one focus.";
  } else if (input.key_goals.length > QUICK_BUILD_KEY_GOAL_CAP) {
    errors.key_goals = `Pick at most ${QUICK_BUILD_KEY_GOAL_CAP} goals.`;
  }
  if (input.weak_areas.length > QUICK_BUILD_WEAK_AREA_CAP) {
    errors.weak_areas = `Pick at most ${QUICK_BUILD_WEAK_AREA_CAP} weak areas.`;
  }
  const sanitizedFocus = sanitizeQuickBuildFocusByDaysOut(input, options?.now);
  if (sanitizedFocus.key_goals.length !== input.key_goals.length) {
    errors.key_goals = "One or more goals are not available for this fight window.";
  }
  if (sanitizedFocus.weak_areas.length !== input.weak_areas.length) {
    errors.weak_areas = "One or more weak areas are not available for this fight window.";
  }

  if (!input.no_scheduled_fight && input.fight_date && !errors.fight_date) {
    const focus = validatePerformanceFocusSelections(
      input.fight_date,
      { keyGoals: input.key_goals, weakAreas: input.weak_areas },
      { now: options?.now, timeZone: options?.timeZone },
    );
    if (focus.isOverCap && focus.errorMessage) {
      errors.focus_cap = focus.errorMessage;
    }
  }

  return errors;
}

export function quickBuildToPlanRequest(input: QuickBuildInput): PlanRequest {
  const trimmedName = input.full_name.trim();
  const base = emptyPlanRequest(trimmedName);
  const keyGoals = retainKnownOptionValues(input.key_goals, KEY_GOAL_OPTIONS);
  const weakAreas = retainKnownOptionValues(input.weak_areas, WEAK_AREA_OPTIONS);
  const plan: PlanRequest = {
    ...base,
    athlete: {
      ...base.athlete,
      full_name: trimmedName,
      technical_style: retainKnownOptionValues(input.technical_style, TECHNICAL_STYLE_OPTIONS),
      tactical_style: retainKnownOptionValues(input.tactical_style, TACTICAL_STYLE_OPTIONS),
      athlete_timezone: base.athlete.athlete_timezone || detectDeviceTimeZone(),
    },
    fight_date: input.no_scheduled_fight ? "" : input.fight_date,
    no_scheduled_fight: input.no_scheduled_fight,
    rounds_format: input.rounds_format || "3 x 3",
    weekly_training_frequency: input.weekly_training_frequency,
    fatigue_level: "low",
    training_availability: retainKnownOptionValues(input.training_availability, TRAINING_AVAILABILITY_OPTIONS),
    hard_sparring_days: retainKnownOptionValues(input.hard_sparring_days, TRAINING_AVAILABILITY_OPTIONS)
      .filter((day) => input.training_availability.includes(day))
      .slice(0, HARD_SPARRING_DAY_CAP),
    support_work_days: [],
    equipment_access: retainKnownOptionValues(input.equipment_access, EQUIPMENT_ACCESS_OPTIONS),
    injuries: input.injuries.trim(),
    key_goals: keyGoals,
    primary_goal: keyGoals[0] ?? "",
    weak_areas: weakAreas,
    primary_weak_area: weakAreas[0] ?? "",
    goal_weakness_collision_detail: "",
    goal_weakness_collision_tags: [],
    goal_weakness_collision_details: [],
    training_preference: "",
    mindset_challenges: "",
    notes: "",
  };
  return canonicalizePerformanceFocus(applyNoScheduledFightSnapshot(plan, input.no_scheduled_fight));
}
