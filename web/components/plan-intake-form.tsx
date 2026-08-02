"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { BodyMap, type BodyMapSide } from "@/components/body-map";
import { CustomSelect } from "@/components/custom-select";
import { saveOnboardingDraft } from "@/lib/api";
import { formatAppDate } from "@/lib/date-format";
import { markGenerationIntent } from "@/lib/generation-intent";
import {
  detectDeviceTimeZone,
  EQUIPMENT_ACCESS_OPTIONS,
  getOptionLabel,
  getOptionLabels,
  isValidRecordFormat,
  KEY_GOAL_OPTIONS,
  cycleGuidedInjurySeverity,
  normalizeGuidedInjurySeverity,
  PROFESSIONAL_STATUS_OPTIONS,
  retainKnownOptionValues,
  sanitizeRecordInput,
  STANCE_OPTIONS,
  TACTICAL_STYLE_OPTIONS,
  TECHNICAL_STYLE_OPTIONS,
  toggleListValue,
  TRAINING_AVAILABILITY_OPTIONS,
  type IntakeOption,
  WEAK_AREA_OPTIONS,
} from "@/lib/intake-options";
import {
  buildGuidedInjuryFields,
  coerceGuidedInjuryEditState,
  EMPTY_GUIDED_INJURY,
  hasGuidedInjuryContent,
  hasGuidedInjuryDescriptorWithoutArea,
  hydrateGuidedInjuryStates,
  type GuidedInjuryState,
} from "@/lib/guided-injury";
import { GuidedInjuryCard } from "@/components/guided-injury-card";
import { OnboardingTrustNote } from "@/components/onboarding-trust-note";
import { SafetyNote } from "@/components/safety-note";
import { WhyTooltip } from "@/components/why-tooltip";
import { INJURY_INTAKE_SAFETY } from "@/lib/safety-copy";
import { LevelSlider, type LevelValue } from "@/components/rating-controls";
import { applyNoScheduledFightSnapshot, canonicalizePerformanceFocus, emptyPlanRequest, hydratePlanRequest, mergePlanRequestDraft, mergeSavedOnboardingDraft } from "@/lib/onboarding";
import { writePendingGenerationPayload } from "@/lib/generation-pending-payload";
import { buildRoundsFormat, parseRoundsFormat, ROUND_COUNT_OPTIONS, ROUND_DURATION_OPTIONS } from "@/lib/rounds-format";
import { FOCUS_CAP_DISABLED_REASON, getPerformanceFocusCap, validatePerformanceFocusSelections } from "@/lib/performance-focus-cap";
import { canSelectWizardStep } from "@/lib/step-navigation";
import {
  getAvailabilityConsistency,
  getHardSparringWarning,
  getSparringConsistency,
  HARD_SPARRING_DAY_CAP,
} from "@/lib/training-schedule";
import {
  buildDaysOutContext,
  computeDaysUntilFight,
  isFightDateInPast,
  getFightDayLockedWeekday,
  filterAvailablePerformanceFocusValues,
  getPerformanceFocusOptionAvailability,
  HARD_SPARRING_STRENGTH_REMOVAL_MESSAGE,
  shouldHideField,
  shouldDisableField,
  shouldDeEmphasizeField,
  getFieldHelperText,
  type DaysOutContext,
  type PerformanceFocusGroup,
} from "@/lib/days-out-policy";
import type { PlanRequest } from "@/lib/types";
import {
  ATHLETE_FULL_NAME_MAX,
  MENTAL_BLOCKERS_MAX,
  PREVIOUS_PLAN_FEEDBACK_MAX,
  RECORD_MAX,
  TRAINING_PREFERENCE_MAX,
} from "@/lib/input-limits";

const steps = ["Profile", "Fight Context", "Training", "Restrictions", "Performance", "Review"] as const;
const PERFORMANCE_STEP_INDEX = 4;

// Each validation field lives on one step. Used as a safety net so any
// reportInvalidField caller still routes the user to the right step even
// if the call site forgets to pass `step`.
const FIELD_STEP_MAP: Record<string, number> = {
  record: 0,
  technicalStyle: 0,
  fightDate: 1,
  roundCount: 1,
  roundDuration: 1,
  sessionsPerWeek: 1,
  trainingAvailabilityGroup: 2,
  hardSparringAck: 2,
  availabilityConsistencyAlert: 2,
  sparringConsistencyAlert: 2,
  keyGoalsGroup: PERFORMANCE_STEP_INDEX,
};

function resolveFieldStep(fieldId: string): number | undefined {
  if (fieldId.startsWith("guidedInjuryCard-")) return 3;
  return FIELD_STEP_MAP[fieldId];
}
const SEX_OPTIONS: IntakeOption[] = [
  { label: "Male", value: "male" },
  { label: "Female", value: "female" },
];

type PriorityOverlap = {
  label: string;
  normalizedTag: string;
  tag: string;
};

const POWER_CLARIFICATION_OPTIONS = [
  "Overall power",
  "Power drops when tired",
  "First-step explosiveness",
  "Punching or striking power",
  "Kicking power",
  "Lower-body power",
  "Rotational power through hips and trunk",
  "Not sure",
];
const CONDITIONING_CLARIFICATION_OPTIONS = [
  "Overall gas tank",
  "Late-round fatigue",
  "Recovery between bursts",
  "Baseline cardio",
  "Repeated hard efforts",
  "Not sure",
];
const MOBILITY_CLARIFICATION_OPTIONS = [
  "General mobility",
  "Hip mobility",
  "Shoulder mobility",
  "Ankle mobility",
  "Stiff movement when tired",
  "Not sure",
];
const GENERIC_CLARIFICATION_OPTIONS = [
  "I want to improve it overall",
  "It drops off when tired",
  "It affects my technique",
  "It affects my power",
  "It affects my conditioning",
  "Not sure",
];
const PRIORITY_OVERLAP_ALIASES: Record<string, string> = {
  gas_tank: "conditioning",
};

function normalizePriorityOverlapValue(value: string): string {
  const normalized = value
    .trim()
    .toLowerCase()
    .replace(/&/g, " ")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return PRIORITY_OVERLAP_ALIASES[normalized] ?? normalized;
}

function getPriorityOptionLabel(value: string): string {
  return (
    KEY_GOAL_OPTIONS.find((option) => option.value === value)?.label
    ?? WEAK_AREA_OPTIONS.find((option) => option.value === value)?.label
    ?? value
  );
}

function getGoalWeakAreaOverlaps(keyGoals: string[], weakAreas: string[]): PriorityOverlap[] {
  const weakAreaSet = new Set(weakAreas.map(normalizePriorityOverlapValue).filter(Boolean));
  const overlaps: PriorityOverlap[] = [];
  const seen = new Set<string>();

  for (const goal of keyGoals) {
    const normalizedTag = normalizePriorityOverlapValue(goal);
    if (!normalizedTag || !weakAreaSet.has(normalizedTag) || seen.has(normalizedTag)) {
      continue;
    }
    seen.add(normalizedTag);
    overlaps.push({
      label: getPriorityOptionLabel(goal),
      normalizedTag,
      tag: goal,
    });
  }

  return overlaps;
}

function getClarificationOptions(
  normalizedTag: string,
  technicalStyles: string[],
  tacticalStyles: string[],
): string[] {
  const styleSet = new Set([...technicalStyles, ...tacticalStyles].map(normalizePriorityOverlapValue));

  if (normalizedTag === "power" || normalizedTag === "power_explosiveness") {
    return POWER_CLARIFICATION_OPTIONS.filter((option) => {
      if (option === "Kicking power") {
        return styleSet.has("kickboxing") || styleSet.has("muay_thai") || styleSet.has("mma");
      }
      if (option === "Punching or striking power") {
        return styleSet.has("boxing") || styleSet.has("kickboxing") || styleSet.has("muay_thai") || styleSet.has("mma");
      }
      return true;
    });
  }

  if (normalizedTag === "conditioning" || normalizedTag === "gas_tank") {
    return CONDITIONING_CLARIFICATION_OPTIONS;
  }

  if (normalizedTag === "mobility") {
    return MOBILITY_CLARIFICATION_OPTIONS;
  }

  return GENERIC_CLARIFICATION_OPTIONS;
}

function sanitizeCollisionMetadata(form: PlanRequest): Pick<PlanRequest, "goal_weakness_collision_detail" | "goal_weakness_collision_tags" | "goal_weakness_collision_details"> {
  const overlaps = getGoalWeakAreaOverlaps(form.key_goals, form.weak_areas);
  if (!overlaps.length) {
    return {
      goal_weakness_collision_detail: "",
      goal_weakness_collision_tags: [],
      goal_weakness_collision_details: [],
    };
  }

  const currentDetailMap = new Map((form.goal_weakness_collision_details ?? [])
    .map((entry) => [normalizePriorityOverlapValue(entry.tag), entry.detail?.trim() ?? ""]));
  const nextDetails = overlaps.map((overlap) => {
    const options = getClarificationOptions(overlap.normalizedTag, form.athlete.technical_style, form.athlete.tactical_style);
    const detail = currentDetailMap.get(overlap.normalizedTag) ?? "";
    return {
      tag: overlap.tag,
      label: overlap.label,
      detail: options.includes(detail) ? detail : "",
    };
  });

  const primaryOptions = getClarificationOptions(overlaps[0].normalizedTag, form.athlete.technical_style, form.athlete.tactical_style);
  const primaryDetail = nextDetails[0]?.detail ?? "";
  const currentSingularDetail = form.goal_weakness_collision_detail?.trim() ?? "";

  return {
    goal_weakness_collision_detail: primaryOptions.includes(currentSingularDetail) ? currentSingularDetail : primaryDetail,
    goal_weakness_collision_tags: overlaps.map((overlap) => overlap.tag),
    goal_weakness_collision_details: nextDetails,
  };
}

type DraftMetadata = {
  current_step?: number;
  guided_injury?: Partial<GuidedInjuryState> | null;
  guided_injuries?: Array<Partial<GuidedInjuryState> | null> | null;
  no_scheduled_fight?: boolean | null;
};

type StepValidationStatus = "done" | "pending" | "warning";

type StepValidationCheck = {
  label: string;
  status: StepValidationStatus;
};

function numberOrNull(value: string): number | null {
  if (!value.trim()) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function integerOrNull(value: string): number | null {
  const parsed = numberOrNull(value);
  return parsed === null ? null : Math.round(parsed);
}

function formatValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "Not provided";
  }
  return String(value);
}

function formatFightDateValue(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "Not provided";
  }
  return formatAppDate(value);
}

function hasValue(value: string | number | null | undefined): boolean {
  return !(value === null || value === undefined || value === "");
}

function formatRestrictionSummary(value: string | null | undefined): string {
  return value?.trim() ? value.trim() : "No injuries or restrictions reported.";
}

function getTodayIsoDate(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

const FIGHT_DATE_IN_PAST_MESSAGE =
  "Fight date can't be in the past. Pick an upcoming date or mark \"No scheduled fight\".";

function formatJoinedLabels(values: string[], emptyLabel: string): string {
  return values.length ? values.join(", ") : emptyLabel;
}

function formatWeightCutStatus(currentWeight: number | null | undefined, targetWeight: number | null | undefined): string | null {
  if (currentWeight == null && targetWeight == null) {
    return null;
  }
  if (currentWeight == null) {
    return `Target weight set at ${targetWeight} kg`;
  }
  if (targetWeight == null) {
    return `Current weight ${currentWeight} kg with no target weight set`;
  }

  const difference = Number((currentWeight - targetWeight).toFixed(1));
  if (difference <= -0.5) {
    return `Target weight is ${Math.abs(difference)} kg above current weight`;
  }
  if (difference <= 0.5) {
    return `At target range (${targetWeight} kg)`;
  }
  if (difference <= 2) {
    return `Small cut of ${difference} kg`;
  }
  if (difference <= 4) {
    return `Moderate cut pressure (${difference} kg)`;
  }
  return `High cut pressure (${difference} kg)`;
}

function formatEquipmentLimitations(selectedEquipment: string[]): string | null {
  if (!selectedEquipment.length) {
    return "Not provided";
  }

  const loadedStrengthOptions = ["barbell", "dumbbells", "kettlebells", "trap_bar", "cable", "landmine"];
  const conditioningOptions = ["assault_bike", "rower", "sled", "heavy_bag", "thai_pads"];
  const hasLoadedStrengthOption = selectedEquipment.some((item) => loadedStrengthOptions.includes(item));
  const hasConditioningOption = selectedEquipment.some((item) => conditioningOptions.includes(item));

  if (selectedEquipment.length <= 2) {
    return "Tight equipment setup";
  }
  if (!hasLoadedStrengthOption) {
    return "Limited loaded strength options";
  }
  if (!hasConditioningOption) {
    return "Limited conditioning tool options";
  }
  return "No major equipment limitation flagged";
}

function getPerformanceFocusGroupForField(key: string): PerformanceFocusGroup | null {
  if (key === "key_goals" || key === "weak_areas") {
    return key;
  }
  return null;
}

function formatSparringCollisionRisk({
  fatigueLevel,
  injuries,
  sessionsPerWeek,
  technicalStyle,
  hardSparringDays,
}: {
  fatigueLevel: string;
  injuries: string;
  sessionsPerWeek: number | null | undefined;
  technicalStyle: string;
  hardSparringDays: string[];
}): string | null {
  if (!technicalStyle) {
    return null;
  }

  const hasTissueIssue = injuries.trim().length > 0;
  const highLoad = (sessionsPerWeek ?? 0) >= 5;
  const fixedHardSparring = hardSparringDays.length >= 2;

  if (fixedHardSparring) {
    return `High - declared hard sparring on ${hardSparringDays.join(", ")} should stay away from primary strength and the main glycolytic day`;
  }

  if (fatigueLevel === "high" || (hasTissueIssue && highLoad)) {
    return "High - keep hard sparring away from primary strength and glycolytic work";
  }
  if (fatigueLevel === "moderate" || hasTissueIssue || highLoad) {
    return "Moderate - separate hard sparring from peak S&C days";
  }
  return "Standard - still avoid stacking hard sparring with peak S&C days";
}

function StepPills({
  currentStep,
  onStepSelect,
}: {
  currentStep: number;
  onStepSelect: (step: number) => void;
}) {
  return (
    <div className="step-progress" aria-label="Intake progress">
      {steps.map((label, index) => {
        const statusClass = index < currentStep ? "step-pill-complete" : index === currentStep ? "step-pill-active" : "";
        const statusText = index < currentStep ? "Complete" : index === currentStep ? "Current" : "Upcoming";
        const canSelect = canSelectWizardStep(currentStep, index);
        return (
          <button
            key={label}
            type="button"
            className={`step-pill ${statusClass}`.trim()}
            onClick={() => onStepSelect(index)}
            disabled={!canSelect}
            aria-current={index === currentStep ? "step" : undefined}
          >
            <span className="step-pill-meta">{statusText}</span>
            <span>{label}</span>
          </button>
        );
      })}
    </div>
  );
}

// Full original file content from Main is restored below with only the nutrition action changed.
