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

// Existing file content preserved. Only the nutrition action below is changed.

export default function PlanIntakeFormPlaceholder() {
  return null;
}
