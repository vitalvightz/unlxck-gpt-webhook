import type { PlanRequest, ProgressMilestone } from "@/lib/types";

export type StageOnePhaseSplit = {
  GPP: number;
  SPP: number;
  TAPER: number;
};

export type StageOneTriage = {
  mode: string;
  parsedInjuryCount: number;
};

export type StageOneCamp = {
  campWeeks: number;
  phaseWeeks: StageOnePhaseSplit;
  isOpenCamp: boolean;
  fightDate: string;
};

export type StageOneFocus = {
  primaryGoal: string;
  keyGoals: string[];
  primaryWeakArea: string;
  weakAreas: string[];
};

export type StageOneSchedule = {
  weeklyTrainingFrequency: number | null;
  availableDays: number;
  trainingAvailability: string[];
  roundsFormat: string;
};

export type StageOneRestrictions = {
  equipmentAccess: string[];
  injuriesText: string;
  parsedInjuryCount: number;
};

export type StageOneSafetyNote = {
  kind: "triage";
  triageMode: string;
  message: string;
};

export type StageOnePreview = {
  camp: StageOneCamp;
  focus: StageOneFocus;
  schedule: StageOneSchedule;
  restrictions: StageOneRestrictions;
  safetyNotes: StageOneSafetyNote[];
};

const CAMP_BRIEF_CODE = "camp_brief_built";
const INJURY_TRIAGE_CODE = "injury_triage_done";

function lastMilestone(
  milestones: ProgressMilestone[] | undefined,
  code: string,
): ProgressMilestone | null {
  if (!Array.isArray(milestones)) {
    return null;
  }
  for (let i = milestones.length - 1; i >= 0; i -= 1) {
    if (milestones[i]?.code === code) {
      return milestones[i];
    }
  }
  return null;
}

function toFinitePositiveInt(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return 0;
  }
  return Math.round(value);
}

function readPhaseWeeks(meta: Record<string, unknown> | undefined): StageOnePhaseSplit {
  const raw = meta?.phase_weeks;
  if (!raw || typeof raw !== "object") {
    return { GPP: 0, SPP: 0, TAPER: 0 };
  }
  const source = raw as Record<string, unknown>;
  return {
    GPP: toFinitePositiveInt(source.GPP),
    SPP: toFinitePositiveInt(source.SPP),
    TAPER: toFinitePositiveInt(source.TAPER),
  };
}

export function selectCampBrief(
  milestones: ProgressMilestone[] | undefined,
): { campWeeks: number; phaseWeeks: StageOnePhaseSplit } | null {
  const milestone = lastMilestone(milestones, CAMP_BRIEF_CODE);
  if (!milestone) {
    return null;
  }
  const meta = (milestone.meta ?? {}) as Record<string, unknown>;
  const campWeeks = toFinitePositiveInt(meta.camp_len);
  const phaseWeeks = readPhaseWeeks(meta);
  const phaseSum = phaseWeeks.GPP + phaseWeeks.SPP + phaseWeeks.TAPER;
  if (campWeeks === 0 && phaseSum === 0) {
    return null;
  }
  return { campWeeks, phaseWeeks };
}

export function selectTriage(
  milestones: ProgressMilestone[] | undefined,
): StageOneTriage | null {
  const milestone = lastMilestone(milestones, INJURY_TRIAGE_CODE);
  if (!milestone) {
    return null;
  }
  const meta = (milestone.meta ?? {}) as Record<string, unknown>;
  const mode = typeof meta.triage_mode === "string" ? meta.triage_mode.trim() : "";
  const parsedInjuryCount = toFinitePositiveInt(meta.parsed_injury_count);
  if (!mode && parsedInjuryCount === 0) {
    return null;
  }
  return {
    mode: mode || "full_plan",
    parsedInjuryCount,
  };
}

function dedupeStrings(values: readonly (string | null | undefined)[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of values) {
    const value = typeof raw === "string" ? raw.trim() : "";
    if (!value) continue;
    const key = value.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(value);
  }
  return out;
}

const TRIAGE_ADVISORY_COPY: Record<string, string> = {
  medical_hold: "Injury triage flagged this for a medical hold. Final plan will reflect that.",
  restricted_rehab_only: "Injury triage routed this to a restricted rehab build.",
  needs_review: "Injury triage flagged this for coach review before release.",
  triage_blocked: "Injury triage blocked Stage 2 finalization until review clears.",
};

function buildSafetyNotes(triage: StageOneTriage | null): StageOneSafetyNote[] {
  if (!triage) return [];
  const normalized = triage.mode.toLowerCase();
  if (!normalized || normalized === "full_plan") {
    return [];
  }
  const message =
    TRIAGE_ADVISORY_COPY[normalized] ??
    `Injury triage mode "${triage.mode}" applied — final plan may route differently.`;
  return [{ kind: "triage", triageMode: triage.mode, message }];
}

export function buildStageOnePreview(
  intake: PlanRequest | null | undefined,
  milestones: ProgressMilestone[] | undefined,
): StageOnePreview | null {
  if (!intake) return null;
  let camp: { campWeeks: number; phaseWeeks: StageOnePhaseSplit } | null = null;
  let triage: StageOneTriage | null = null;
  try {
    camp = selectCampBrief(milestones);
    triage = selectTriage(milestones);
  } catch {
    return null;
  }
  if (!camp) return null;

  const isOpenCamp = intake.no_scheduled_fight === true;
  const trainingAvailability = dedupeStrings(intake.training_availability ?? []);
  const equipmentAccess = dedupeStrings(intake.equipment_access ?? []);
  const keyGoals = dedupeStrings(intake.key_goals ?? []);
  const weakAreas = dedupeStrings(intake.weak_areas ?? []);
  const primaryGoal = typeof intake.primary_goal === "string" ? intake.primary_goal.trim() : "";
  const primaryWeakArea =
    typeof intake.primary_weak_area === "string" ? intake.primary_weak_area.trim() : "";

  const weekly =
    typeof intake.weekly_training_frequency === "number" && Number.isFinite(intake.weekly_training_frequency)
      ? intake.weekly_training_frequency
      : null;

  const injuriesText = typeof intake.injuries === "string" ? intake.injuries.trim() : "";

  return {
    camp: {
      campWeeks: camp.campWeeks,
      phaseWeeks: camp.phaseWeeks,
      isOpenCamp,
      fightDate: isOpenCamp ? "" : intake.fight_date || "",
    },
    focus: {
      primaryGoal,
      keyGoals,
      primaryWeakArea,
      weakAreas,
    },
    schedule: {
      weeklyTrainingFrequency: weekly,
      availableDays: trainingAvailability.length,
      trainingAvailability,
      roundsFormat: typeof intake.rounds_format === "string" ? intake.rounds_format.trim() : "",
    },
    restrictions: {
      equipmentAccess,
      injuriesText,
      parsedInjuryCount: triage?.parsedInjuryCount ?? 0,
    },
    safetyNotes: buildSafetyNotes(triage),
  };
}
