"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations, useTranslations as useAppTranslations } from "next-intl";
import { useEffect, useRef, useState, useTransition } from "react";
import { translateUiText } from "@/i18n/ui-text";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { BodyMap, type BodyMapSide } from "@/components/body-map";
import { CustomSelect } from "@/components/custom-select";
import { EquipmentSelector } from "@/components/equipment-selector";
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
import { hasHealthDataConsent } from "@/lib/compliance";
import { HEALTH_CONSENT_BLOCKED_MESSAGE, withoutIntakeHealthData } from "@/lib/health-consent-ui";
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
    const appText = useAppTranslations("AppText");
  return (
    <div className="step-progress" aria-label={appText("text_22492da005a2")}>
      {steps.map((label, index) => {
        const statusClass = index < currentStep ? "step-pill-complete" : index === currentStep ? "step-pill-active" : "";
        const statusText = index < currentStep ? "Complete" : index === currentStep ? "Current" : "Upcoming";
        const pillContent = (
          <>
            <span className="step-pill-index">{String(index + 1).padStart(2, "0")}</span>
            <div>
              <div className="step-pill-title">{label}</div>
              <p className="step-pill-meta">{statusText}</p>
            </div>
          </>
        );

        return (
          <button
            key={label}
            type="button"
            className={`step-pill step-pill-button ${statusClass}`.trim()}
            onClick={() => onStepSelect(index)}
            aria-current={index === currentStep ? "step" : undefined}
          >
            {pillContent}
          </button>
        );
      })}
    </div>
  );
}

function AutoSaveIndicator({
  status,
  lastSavedAt,
  onRetry,
  retryDisabled,
}: {
  status: "idle" | "saving" | "saved" | "error";
  lastSavedAt: number | null;
  onRetry: () => void;
  retryDisabled: boolean;
}) {
    const appText = useAppTranslations("AppText");
  if (status === "idle" && lastSavedAt === null) {
    return null;
  }
  const label =
    status === "saving"
      ? "Saving draft…"
      : status === "error"
        ? "Couldn't save draft"
        : "Draft saved";
  return (
    <p className={`onboarding-save-indicator onboarding-save-indicator-${status === "idle" ? "saved" : status}`} aria-live="polite">
      <span className="onboarding-save-indicator-dot" aria-hidden="true" />
      <span>{label}</span>
      {status === "error" ? (
        <button type="button" className="onboarding-save-indicator-retry" onClick={onRetry} disabled={retryDisabled}>
          {appText("text_942087cc2d41")}</button>
      ) : null}
    </p>
  );
}

function getOnboardingProgressState(currentStep: number) {
  const stepNumber = currentStep + 1;
  const totalSteps = steps.length;
  const remainingSteps = Math.max(totalSteps - stepNumber, 0);

  return {
    stepNumber,
    totalSteps,
    progressValue: (stepNumber / totalSteps) * 100,
    badgeText: remainingSteps === 0 ? "Ready" : "In progress",
    helperText:
      remainingSteps === 0
        ? "All intake steps are complete. Review your answers, then generate the plan."
        : `${remainingSteps} step${remainingSteps === 1 ? "" : "s"} remaining before plan generation.`,
  };
}

function OnboardingProgressStrip({
  currentStep,
  isExpandable = false,
  isExpanded = false,
  onToggle,
  controlsId,
}: {
  currentStep: number;
  isExpandable?: boolean;
  isExpanded?: boolean;
  onToggle?: () => void;
  controlsId?: string;
}) {
    const appText = useAppTranslations("AppText");
  const progress = getOnboardingProgressState(currentStep);
  const content = (
    <>
      <div className="onboarding-progress-strip-topline">
        <p className="kicker">{appText("text_22492da005a2")}</p>
        <span
          className={`onboarding-progress-badge ${progress.badgeText === "Ready" ? "onboarding-progress-badge-ready" : ""}`.trim()}
        >
          {progress.badgeText}
        </span>
      </div>
      <p className="onboarding-progress-strip-title">
        {appText("text_8e6a6cca7aae")}{progress.stepNumber} {appText("text_28391d3bc64e")}{progress.totalSteps}
      </p>
      <div className="overview-progress-track onboarding-progress-track" role="presentation" aria-hidden="true">
        <span className="overview-progress-fill onboarding-progress-fill" style={{ width: `${progress.progressValue}%` }} />
      </div>
      <div className="onboarding-progress-strip-footer">
        <p className="overview-progress-helper onboarding-progress-helper">{progress.helperText}</p>
        {isExpandable ? (
          <span className="onboarding-progress-affordance" aria-hidden="true">
            <span className="onboarding-progress-affordance-label">{isExpanded ? appText("text_7d9eb7acb13e") : appText("text_7384c91d94c6")}</span>
            <span className="onboarding-progress-chevron" />
          </span>
        ) : null}
      </div>
    </>
  );

  if (isExpandable && onToggle && controlsId) {
    return (
      <button
        type="button"
        className="onboarding-progress-strip onboarding-progress-strip-button onboarding-mobile-step-trigger"
        aria-expanded={isExpanded}
        aria-controls={controlsId}
        onClick={onToggle}
      >
        {content}
      </button>
    );
  }

  return <div className="onboarding-progress-strip">{content}</div>;
}

function MobileStepRail({
  currentStep,
  onStepSelect,
}: {
  currentStep: number;
  onStepSelect: (step: number) => void;
}) {
    const appText = useAppTranslations("AppText");
  const railRef = useRef<HTMLDivElement | null>(null);
  const itemRefs = useRef<Array<HTMLElement | null>>([]);

  useEffect(() => {
    const rail = railRef.current;
    const activeItem = itemRefs.current[currentStep];
    if (!rail || !activeItem) {
      return;
    }

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const itemCenter = activeItem.offsetLeft + activeItem.offsetWidth / 2;
    const targetLeft = Math.max(itemCenter - rail.clientWidth / 2, 0);
    const maxScrollLeft = Math.max(rail.scrollWidth - rail.clientWidth, 0);

    rail.scrollTo({
      left: Math.min(targetLeft, maxScrollLeft),
      behavior: reducedMotion ? "auto" : "smooth",
    });
  }, [currentStep]);

  return (
    <div className="mobile-step-rail" data-state="open">
      <div ref={railRef} className="mobile-step-rail-scroll" aria-label={appText("text_1bdccfa8e4ef")}>
        {steps.map((label, index) => {
          const statusClass = index < currentStep ? "mobile-step-rail-item-complete" : index === currentStep ? "mobile-step-rail-item-active" : "";
          const pillContent = (
            <>
              <span className="mobile-step-rail-index">{String(index + 1).padStart(2, "0")}</span>
              <span className="mobile-step-rail-label">{label}</span>
            </>
          );

          return (
            <button
              key={label}
              type="button"
              ref={(node) => {
                itemRefs.current[index] = node;
              }}
              className={`mobile-step-rail-item ${statusClass}`.trim()}
              onClick={() => onStepSelect(index)}
              aria-current={index === currentStep ? "step" : undefined}
              aria-label={`${label}, step ${index + 1}, ${index < currentStep ? "complete" : index === currentStep ? "current" : "upcoming"}`}
            >
              {pillContent}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function MobileOnboardingHeader({
  currentStep,
  isOpen,
  onToggle,
  onStepSelect,
  saveStatus,
  lastSavedAt,
  onRetrySave,
  retrySaveDisabled,
}: {
  currentStep: number;
  isOpen: boolean;
  onToggle: () => void;
  onStepSelect: (step: number) => void;
  saveStatus: "idle" | "saving" | "saved" | "error";
  lastSavedAt: number | null;
  onRetrySave: () => void;
  retrySaveDisabled: boolean;
}) {
    const appText = useAppTranslations("AppText");
  return (
    <div className="onboarding-heading-mobile">
      <div className="onboarding-mobile-header-copy">
        <p className="kicker">{appText("text_2cd602ade4a6")}</p>
        <p className="onboarding-mobile-title">{appText("text_97b9f3ff127d")}</p>
        <p className="muted">{appText("text_ab3f8d47c2e2")}</p>
        <Link href="/quick-build" className="ghost-button onboarding-quick-build-link">
          {appText("text_0cfd4a365725")}</Link>
      </div>
      <OnboardingProgressStrip
        currentStep={currentStep}
        isExpandable
        isExpanded={isOpen}
        onToggle={onToggle}
        controlsId="onboarding-mobile-steps"
      />
      <AutoSaveIndicator
        status={saveStatus}
        lastSavedAt={lastSavedAt}
        onRetry={onRetrySave}
        retryDisabled={retrySaveDisabled}
      />
      {isOpen ? (
        <div id="onboarding-mobile-steps" className="onboarding-mobile-progress-panel">
          <MobileStepRail currentStep={currentStep} onStepSelect={onStepSelect} />
        </div>
      ) : null}
    </div>
  );
}

function CheckboxGroup({
  id,
  label,
  options,
  selectedValues,
  onToggle,
  disableAdditionalSelections = false,
  capDisabledReason,
  disableAll = false,
  getOptionDisabledReason,
  invalid = false,
  describedBy,
  hideLabel = false,
}: {
  id?: string;
  label: string;
  options: IntakeOption[];
  selectedValues: string[];
  onToggle: (value: string) => void;
  disableAdditionalSelections?: boolean;
  capDisabledReason?: string;
  disableAll?: boolean;
  getOptionDisabledReason?: (option: IntakeOption, checked: boolean) => string | null;
  invalid?: boolean;
  describedBy?: string;
  hideLabel?: boolean;
}) {
    const appText = useAppTranslations("AppText");
  return (
    <div
      id={id}
      className={`field${invalid ? " field-invalid" : ""}`}
      role="group"
      aria-label={label}
      aria-describedby={describedBy}
      tabIndex={invalid ? -1 : undefined}
    >
      <span className={`checkbox-group-label${hideLabel ? " sr-only" : ""}`}>{label}</span>
      <div className="checkbox-grid">
        {options.map((option) => {
          const checked = selectedValues.includes(option.value);
          const daysOutDisabledReason = getOptionDisabledReason?.(option, checked) ?? null;
          const capDisabled = disableAdditionalSelections && !checked;
          const disabled = disableAll || Boolean(daysOutDisabledReason) || capDisabled;
          const labelTitle = daysOutDisabledReason ?? (capDisabled ? capDisabledReason ?? "Focus cap reached." : undefined);
          return (
            <label
              key={option.value}
              className={`checkbox-card ${checked ? "checkbox-card-checked" : ""} ${disabled ? "checkbox-card-disabled" : ""}`.trim()}
              aria-disabled={disabled}
              title={labelTitle}
            >
              <input
                type="checkbox"
                checked={checked}
                disabled={disabled}
                aria-invalid={invalid ? true : undefined}
                aria-describedby={describedBy}
                onChange={() => onToggle(option.value)}
              />
              <span className="checkbox-card-copy">
                <span className="checkbox-card-title">{translateUiText(appText, option.label)}</span>
              </span>
              {labelTitle ? (
                <WhyTooltip
                  title={appText("text_ca1844969742")}
                  body={labelTitle}
                  triggerLabel="?"
                  ariaLabel={`Why ${translateUiText(appText, option.label)} is unavailable`}
                />
              ) : null}
            </label>
          );
        })}
      </div>
    </div>
  );
}

function OptionalDetails({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
    const appText = useAppTranslations("AppText");
  return (
    <details className="overview-disclosure onboarding-optional-disclosure">
      <summary className="overview-disclosure-summary">
        <div className="overview-disclosure-copy">
          <p className="kicker">{appText("text_59be71333c96")}</p>
          <p className="overview-disclosure-title">{title}</p>
          {hint ? <p className="muted">{hint}</p> : null}
        </div>
        <span className="overview-disclosure-meta">
          <span className="overview-disclosure-chevron" aria-hidden="true" />
        </span>
      </summary>
      <div className="overview-disclosure-body">{children}</div>
    </details>
  );
}

function ReviewDetailList({ items }: { items: Array<{ label: string; value: string }> }) {
  return (
    <div className="review-detail-list">
      {items.map((item) => (
        <div key={`${item.label}-${item.value}`} className="review-detail-row">
          <p className="review-detail-label">{item.label}</p>
          <p className="review-detail-value">{item.value}</p>
        </div>
      ))}
    </div>
  );
}

function StepValidationPanel({
  stepLabel,
  title,
  description,
  checks,
}: {
  stepLabel: string;
  title: string;
  description: string;
  checks: StepValidationCheck[];
}) {
    const appText = useAppTranslations("AppText");
  const unresolvedChecks = checks.filter((check) => check.status !== "done");

  return (
    <div
      className={`support-panel onboarding-validation-panel ${unresolvedChecks.length ? "onboarding-validation-panel-attention" : "onboarding-validation-panel-ready"}`.trim()}
      role="status"
      aria-live="polite"
    >
      <div className="onboarding-validation-header">
        <div className="onboarding-validation-copy">
          <p className="kicker">{stepLabel} {appText("text_20f65c28671b")}</p>
          <h2 className="form-section-title">{title}</h2>
          <p className="muted">{description}</p>
        </div>
        <span
          className={`onboarding-validation-badge ${unresolvedChecks.length ? "" : "onboarding-validation-badge-ready"}`.trim()}
        >
          {unresolvedChecks.length ? `${unresolvedChecks.length} left` : appText("text_5fa7aac5375c")}
        </span>
      </div>
      <ul className="summary-list onboarding-validation-list">
        {checks.map((check) => (
          <li key={`${check.status}-${check.label}`} className="onboarding-validation-item" data-status={check.status}>
            {check.label}
          </li>
        ))}
      </ul>
    </div>
  );
}

function getReviewStepBlockingIssue(
  nextForm: PlanRequest,
  options: {
    hardSparringWarningLocked: boolean;
    noScheduledFight: boolean;
  },
): { message: string; step: number; fieldId: string } | null {
  if (!isValidRecordFormat(nextForm.athlete.record ?? "")) return { message: "Record must use x-x or x-x-x format, like 5-1 or 12-2-1.", step: 0, fieldId: "record" };
  if (!nextForm.athlete.technical_style.length) return { message: "Select a combat sport before continuing to review.", step: 0, fieldId: "technicalStyle" };
  if (!nextForm.fight_date && !options.noScheduledFight) return { message: "Choose your fight date or mark \"No scheduled fight\" before continuing to review.", step: 1, fieldId: "fightDate" };
  if (!options.noScheduledFight && isFightDateInPast(nextForm.fight_date)) return { message: FIGHT_DATE_IN_PAST_MESSAGE, step: 1, fieldId: "fightDate" };
  if (!nextForm.training_availability.length) return { message: "Pick at least one training availability option before continuing to review.", step: 2, fieldId: "trainingAvailabilityGroup" };
  if (!nextForm.weekly_training_frequency || nextForm.weekly_training_frequency < 1) return { message: "Planned sessions per week must be at least 1.", step: 1, fieldId: "sessionsPerWeek" };
  if (nextForm.weekly_training_frequency > 6) return { message: "Planned sessions per week cannot exceed 6.", step: 1, fieldId: "sessionsPerWeek" };
  const parsedRounds = parseRoundsFormat(nextForm.rounds_format);
  if (!parsedRounds.roundCount) return { message: "Choose both round count and round duration before continuing to review.", step: 1, fieldId: "roundCount" };
  if (!parsedRounds.roundDuration) return { message: "Choose both round count and round duration before continuing to review.", step: 1, fieldId: "roundDuration" };
  if (options.hardSparringWarningLocked) {
    return { message: "Acknowledge the hard sparring warning in the Training step before continuing to review.", step: 2, fieldId: "hardSparringAck" };
  }
  const focusValidation = validatePerformanceFocusSelections(
    nextForm.fight_date,
    { keyGoals: nextForm.key_goals, weakAreas: nextForm.weak_areas },
    { timeZone: nextForm.athlete.athlete_timezone },
  );
  if (focusValidation.isOverCap) {
    return {
      message: focusValidation.errorMessage ?? "Goals and weak areas exceed the current cap. Update your selections before continuing.",
      step: PERFORMANCE_STEP_INDEX,
      fieldId: "keyGoalsGroup",
    };
  }
  return null;
}

function syncDeviceFields(current: PlanRequest): PlanRequest {
  const detectedTimeZone = detectDeviceTimeZone();
  return {
    ...current,
    athlete: {
      ...current.athlete,
      athlete_timezone: detectedTimeZone || current.athlete.athlete_timezone || "",
    },
  };
}

const WEEKDAY_FROM_ISO_DATE = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

function getWeekdayFromIsoDate(dateValue: string): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateValue);
  if (!match) return null;

  const year = Number(match[1]);
  const monthIndex = Number(match[2]) - 1;
  const day = Number(match[3]);
  const parsed = new Date(Date.UTC(year, monthIndex, day));

  if (Number.isNaN(parsed.getTime())) return null;
  return WEEKDAY_FROM_ISO_DATE[parsed.getUTCDay()] ?? null;
}

type TrainingGateAction = "save_draft" | "next" | "step_select" | "generate";

type TrainingGateDecision =
  | { kind: "allow" }
  | { kind: "hard_error"; message: string; source: "availability" | "sparring" }
  | { kind: "warning_ack_required"; message: string; shouldRedirectToTraining: boolean };

export function PlanIntakeForm() {
    const appText = useAppTranslations("AppText");
  const t = useTranslations("Onboarding");
  const router = useRouter();
  const searchParams = useSearchParams();
  const refiningFromQuickBuild = searchParams.get("from") === "quick_build";
  const { me, session, replaceMe } = useAppSession();
  // Server-derived age band; the client never decides this.
  const isMinorAthlete = Boolean(me?.profile.is_minor);
  const healthConsentGranted = hasHealthDataConsent(me);
  const [currentStep, setCurrentStep] = useState(0);
  const [isMobileProgressOpen, setIsMobileProgressOpen] = useState(false);
  const [form, setForm] = useState<PlanRequest>(emptyPlanRequest());
  const [guidedInjuries, setGuidedInjuries] = useState<GuidedInjuryState[]>([]);
  const [activeGuidedInjuryIndex, setActiveGuidedInjuryIndex] = useState<number | null>(null);
  const [noRestrictions, setNoRestrictions] = useState(true);
  const [showClearInjuriesConfirm, setShowClearInjuriesConfirm] = useState(false);
  const [bodyMapSide, setBodyMapSide] = useState<BodyMapSide>("front");
  const [noScheduledFight, setNoScheduledFight] = useState(false);
  const [pendingInjuryRemovalIndex, setPendingInjuryRemovalIndex] = useState<number | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const [acknowledgedHardSparringWarningKey, setAcknowledgedHardSparringWarningKey] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [lastSavedAt, setLastSavedAt] = useState<number | null>(null);
  const [invalidFieldId, setInvalidFieldId] = useState<string | null>(null);
  const [validationFocusRequest, setValidationFocusRequest] = useState<{ fieldId: string; nonce: number } | null>(null);
  const lastSavedSnapshotRef = useRef<string>("");
  const issueRedirectConsumedRef = useRef(false);
  const pendingRemovalRef = useRef<HTMLDivElement | null>(null);
  const recordHasError = !isValidRecordFormat(form.athlete.record ?? "");

    // ── Days-out policy: compute field visibility/disablement ───────────
  const daysUntilFight = computeDaysUntilFight(form.fight_date);
  const hasHardSparring = form.hard_sparring_days.length > 0;
  const daysOutCtx: DaysOutContext = buildDaysOutContext(daysUntilFight, { hasHardSparring });
  const fightDateWeekday = noScheduledFight ? null : getWeekdayFromIsoDate(form.fight_date);
  // Only fight week locks the weekday out of the combat-load tags. Earlier
  // instances of the same weekday are ordinary training days, and the backend
  // fight-day override already clamps the real fight day on the final week.
  const lockedFightWeekday = getFightDayLockedWeekday(fightDateWeekday, daysUntilFight);

  useEffect(() => {
    if (!lockedFightWeekday) {
      return;
    }

    const lockedDay = lockedFightWeekday.trim().toLowerCase();

    setForm((current) => {
      const hardSparringDays = current.hard_sparring_days.filter(
        (day) => day.trim().toLowerCase() !== lockedDay,
      );
      const supportWorkDays = current.support_work_days.filter(
        (day) => day.trim().toLowerCase() !== lockedDay,
      );

      if (
        hardSparringDays.length === current.hard_sparring_days.length &&
        supportWorkDays.length === current.support_work_days.length
      ) {
        return current;
      }

      return {
        ...current,
        hard_sparring_days: hardSparringDays,
        support_work_days: supportWorkDays,
      };
    });
  }, [lockedFightWeekday]);

  useEffect(() => {
    if (!me || hydrated) {
      return;
    }
    const nextForm = syncDeviceFields(hydratePlanRequest(me));
    const draft = (me.profile.onboarding_draft as DraftMetadata | null | undefined) ?? null;
    const nextGuidedInjuries = hydrateGuidedInjuryStates({
      injuries: nextForm.injuries,
      guided_injury: draft?.guided_injury ?? nextForm.guided_injury,
      guided_injuries: draft?.guided_injuries ?? nextForm.guided_injuries,
    });
    const nextGuidedInjuryFields = buildGuidedInjuryFields(nextGuidedInjuries);
    const hasStoredRestrictions = Boolean(
      nextGuidedInjuryFields.injuries || nextForm.injuries?.trim() || nextGuidedInjuries.some((injury) => hasGuidedInjuryContent(injury)),
    );

    setForm({
      ...nextForm,
      ...nextGuidedInjuryFields,
    });
    setGuidedInjuries(nextGuidedInjuries);
    setActiveGuidedInjuryIndex(nextGuidedInjuries.length ? 0 : null);
    setNoRestrictions(!hasStoredRestrictions);
    setNoScheduledFight(Boolean(draft?.no_scheduled_fight ?? nextForm.no_scheduled_fight));
    const savedStep = Number(draft?.current_step ?? 0);
    setCurrentStep(Number.isFinite(savedStep) ? Math.min(Math.max(savedStep, 0), steps.length - 1) : 0);
    setHydrated(true);
  }, [hydrated, me]);

  useEffect(() => {
    if (!healthConsentGranted) {
      setForm((current) => withoutIntakeHealthData(current));
      setGuidedInjuries([]);
      setNoRestrictions(true);
      setActiveGuidedInjuryIndex(null);
    }
  }, [healthConsentGranted]);

  useEffect(() => {
    // Skip top-scroll when a validation focus is pending — the focus effect
    // will scroll the user directly to the invalid field instead.
    if (validationFocusRequest) {
      return;
    }
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reducedMotion ? "instant" : "smooth" });
    // We intentionally do not depend on validationFocusRequest here — its
    // presence is checked at fire time, and adding it would re-trigger
    // scroll-to-top whenever a validation focus completes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentStep]);

  useEffect(() => {
    // When a removal is requested the confirm panel mounts above the map, which
    // can be off-screen on mobile. Bring it into view so the athlete sees the
    // confirm action instead of just the card's × turning red.
    if (pendingInjuryRemovalIndex === null) {
      return;
    }
    const node = pendingRemovalRef.current;
    if (!node) {
      return;
    }
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    node.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "center" });
  }, [pendingInjuryRemovalIndex]);

  useEffect(() => {
    if (!invalidFieldId) {
      return;
    }
    const parsed = parseRoundsFormat(form.rounds_format);
    const isFieldNowValid = (() => {
      switch (invalidFieldId) {
        case "record":
          return isValidRecordFormat(form.athlete.record ?? "");
        case "technicalStyle":
          return form.athlete.technical_style.length > 0;
        case "fightDate":
          return Boolean(form.fight_date) || noScheduledFight;
        case "roundCount":
          return Boolean(parsed.roundCount);
        case "roundDuration":
          return Boolean(parsed.roundDuration);
        case "sessionsPerWeek":
          return Boolean(form.weekly_training_frequency)
            && (form.weekly_training_frequency ?? 0) >= 1
            && (form.weekly_training_frequency ?? 0) <= 6;
        case "trainingAvailabilityGroup":
          return form.training_availability.length > 0;
        case "keyGoalsGroup":
          return !validatePerformanceFocusSelections(
            form.fight_date,
            { keyGoals: form.key_goals, weakAreas: form.weak_areas },
            { timeZone: form.athlete.athlete_timezone },
          ).isOverCap;
        case "hardSparringAck": {
          const warning = getHardSparringWarning(form.hard_sparring_days, form.weekly_training_frequency);
          const ack = acknowledgedHardSparringWarningKey === warning.acknowledgementContextKey;
          return !warning.requiresAcknowledgement || ack;
        }
        case "availabilityConsistencyAlert":
          return !getAvailabilityConsistency(form.training_availability, form.weekly_training_frequency).hardError;
        case "sparringConsistencyAlert":
          return !getSparringConsistency(
            form.training_availability,
            form.hard_sparring_days,
            form.support_work_days,
            !noScheduledFight,
          ).hardError;
        default:
          if (invalidFieldId.startsWith("guidedInjuryCard-")) {
            if (guidedInjuries.some((injury) => hasGuidedInjuryDescriptorWithoutArea(injury))) {
              return false;
            }
            if (noRestrictions) {
              return true;
            }
            return guidedInjuries.some(
              (injury) => Boolean(injury.injury_type) || Boolean(injury.notes.trim()),
            );
          }
          return false;
      }
    })();
    if (isFieldNowValid) {
      setInvalidFieldId(null);
      setError(null);
    }
  }, [
    invalidFieldId,
    form,
    noScheduledFight,
    acknowledgedHardSparringWarningKey,
    guidedInjuries,
    noRestrictions,
  ]);

  useEffect(() => {
    if (!validationFocusRequest) {
      return;
    }
    const { fieldId } = validationFocusRequest;
    let cancelled = false;
    let rafHandle: number | null = null;
    let timeoutHandle: number | null = null;

    function tryFocus(attemptsLeft: number) {
      if (cancelled) return;
      const el = document.getElementById(fieldId);
      if (!el) {
        // The target step may still be mounting (e.g. on cross-step navigation).
        // Retry a few frames before giving up so we never silently no-op.
        if (attemptsLeft > 0) {
          timeoutHandle = window.setTimeout(() => tryFocus(attemptsLeft - 1), 40);
        }
        return;
      }

      // Expand any ancestor <details> blocks (e.g. "Add more detail") so the field is visible.
      let cursor: HTMLElement | null = el.parentElement;
      while (cursor) {
        if (cursor instanceof HTMLDetailsElement && !cursor.open) {
          cursor.open = true;
        }
        cursor = cursor.parentElement;
      }

      const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      el.scrollIntoView({ behavior: reducedMotion ? "instant" : "smooth", block: "start" });

      const isMobile = window.matchMedia("(max-width: 720px)").matches;
      const isTextInput = el instanceof HTMLInputElement && /^(text|email|number|tel|search|url)$/i.test(el.type);
      const isTextarea = el instanceof HTMLTextAreaElement;
      // Skip auto-focus on mobile for text inputs to avoid the keyboard popping up
      // unexpectedly; visual highlight + scroll still leads the user to the field.
      const skipFocus = isMobile && (isTextInput || isTextarea);
      const focusable = el instanceof HTMLInputElement
        || el instanceof HTMLTextAreaElement
        || el instanceof HTMLSelectElement
        || el instanceof HTMLButtonElement
        || el.hasAttribute("tabindex");
      if (!skipFocus && focusable) {
        el.focus({ preventScroll: true });
      }
    }

    // Wait one frame so React has committed the latest render (step change,
    // conditional rendering of the warning panel) before we look for the
    // element. Up to 5 retries handle slower mounts on cross-step nav.
    rafHandle = window.requestAnimationFrame(() => tryFocus(5));

    return () => {
      cancelled = true;
      if (rafHandle !== null) window.cancelAnimationFrame(rafHandle);
      if (timeoutHandle !== null) window.clearTimeout(timeoutHandle);
    };
  }, [validationFocusRequest]);

  const performanceFocusValidation = validatePerformanceFocusSelections(
    form.fight_date,
    {
      keyGoals: form.key_goals,
      weakAreas: form.weak_areas,
    },
    {
      timeZone: form.athlete.athlete_timezone,
    },
  );

  useEffect(() => {
    if (!hydrated || daysUntilFight === null) {
      return;
    }

    const currentDaysOutCtx = buildDaysOutContext(daysUntilFight, { hasHardSparring });
    const nextKeyGoals = filterAvailablePerformanceFocusValues(currentDaysOutCtx, "key_goals", form.key_goals);
    const nextWeakAreas = filterAvailablePerformanceFocusValues(currentDaysOutCtx, "weak_areas", form.weak_areas);
    if (nextKeyGoals.length === form.key_goals.length && nextWeakAreas.length === form.weak_areas.length) {
      return;
    }

    const removedStrengthForHardSparring =
      currentDaysOutCtx.hasHardSparring &&
      currentDaysOutCtx.daysOut !== null &&
      currentDaysOutCtx.daysOut <= 20 &&
      (form.key_goals.includes("strength") || form.weak_areas.includes("strength"));

    setForm((current) => {
      const nextDaysOutCtx = buildDaysOutContext(daysUntilFight, {
        hasHardSparring: current.hard_sparring_days.length > 0,
      });
      const filteredKeyGoals = filterAvailablePerformanceFocusValues(nextDaysOutCtx, "key_goals", current.key_goals);
      const filteredWeakAreas = filterAvailablePerformanceFocusValues(nextDaysOutCtx, "weak_areas", current.weak_areas);

      return {
        ...current,
        key_goals: filteredKeyGoals,
        primary_goal: current.primary_goal && !filteredKeyGoals.includes(current.primary_goal) ? "" : current.primary_goal,
        weak_areas: filteredWeakAreas,
        primary_weak_area: current.primary_weak_area && !filteredWeakAreas.includes(current.primary_weak_area) ? "" : current.primary_weak_area,
      };
    });
    setMessage(
      removedStrengthForHardSparring
        ? HARD_SPARRING_STRENGTH_REMOVAL_MESSAGE
        : "Some picks were removed because they are not available this close to fight day.",
    );
    setError(null);
  }, [daysUntilFight, form.key_goals, form.weak_areas, hasHardSparring, hydrated]);

  useEffect(() => {
    if (!hydrated) return;
    setForm((current) => {
      const next: PlanRequest = { ...current };
      let changed = false;
      const selectedGoals = current.key_goals;
      const selectedWeakAreas = current.weak_areas;

      if (selectedGoals.length === 1) {
        const onlyGoal = selectedGoals[0];
        if (current.primary_goal !== onlyGoal) {
          next.primary_goal = onlyGoal;
          changed = true;
        }
      } else if (current.primary_goal && !selectedGoals.includes(current.primary_goal)) {
        next.primary_goal = "";
        changed = true;
      }

      if (selectedWeakAreas.length === 1) {
        const onlyWeakArea = selectedWeakAreas[0];
        if (current.primary_weak_area !== onlyWeakArea) {
          next.primary_weak_area = onlyWeakArea;
          changed = true;
        }
      } else if (current.primary_weak_area && !selectedWeakAreas.includes(current.primary_weak_area)) {
        next.primary_weak_area = "";
        changed = true;
      }

      return changed ? next : current;
    });
  }, [form.key_goals, form.primary_goal, form.primary_weak_area, form.weak_areas, hydrated]);

  useEffect(() => {
    if (!hydrated) return;
    setForm((current) => {
      const collisionMetadata = sanitizeCollisionMetadata(current);
      const currentTags = current.goal_weakness_collision_tags ?? [];
      const nextTags = collisionMetadata.goal_weakness_collision_tags ?? [];
      const tagsChanged = currentTags.join("|") !== nextTags.join("|");
      const detailChanged = (current.goal_weakness_collision_detail ?? "") !== collisionMetadata.goal_weakness_collision_detail;
      const detailsChanged = JSON.stringify(current.goal_weakness_collision_details ?? []) !== JSON.stringify(collisionMetadata.goal_weakness_collision_details ?? []);

      if (!tagsChanged && !detailChanged && !detailsChanged) {
        return current;
      }

      return {
        ...current,
        ...collisionMetadata,
      };
    });
  }, [
    form.athlete.tactical_style,
    form.athlete.technical_style,
    form.goal_weakness_collision_detail,
    form.goal_weakness_collision_tags,
    form.goal_weakness_collision_details,
    form.key_goals,
    form.weak_areas,
    hydrated,
  ]);


  useEffect(() => {
    if (!hydrated || issueRedirectConsumedRef.current) {
      return;
    }

    const params = new URLSearchParams(window.location.search);
    if (params.get("issue") !== "focus-cap") {
      return;
    }

    issueRedirectConsumedRef.current = true;
    setMessage(null);
    setError(
      performanceFocusValidation.errorMessage
        ?? "This saved intake is over the current focus cap. Remove some goal or weak-area selections before generating.",
    );
    setInvalidFieldId("keyGoalsGroup");
    setValidationFocusRequest({ fieldId: "keyGoalsGroup", nonce: Date.now() });
    setCurrentStep(PERFORMANCE_STEP_INDEX);
    setIsMobileProgressOpen(true);
    router.replace("/onboarding", { scroll: false });
  }, [hydrated, performanceFocusValidation.errorMessage, router]);

  function buildFormSnapshot(
    currentForm: PlanRequest = form,
    currentGuidedInjuries: GuidedInjuryState[] = guidedInjuries,
    currentNoRestrictions: boolean = noRestrictions,
  ): PlanRequest {
    const nextGuidedInjuryFields = buildGuidedInjuryFields(currentGuidedInjuries, {
      noRestrictions: currentNoRestrictions,
    });
    const withGuidedAndCollision = {
      ...currentForm,
      ...nextGuidedInjuryFields,
      ...sanitizeCollisionMetadata({
        ...currentForm,
        ...nextGuidedInjuryFields,
      }),
    };
    const safeForm = healthConsentGranted ? withGuidedAndCollision : withoutIntakeHealthData(withGuidedAndCollision);
    return canonicalizePerformanceFocus(syncDeviceFields(applyNoScheduledFightSnapshot(safeForm, noScheduledFight)));
  }

  function syncGuidedInjuryFields(nextGuidedInjuries: GuidedInjuryState[], nextNoRestrictions: boolean) {
    const nextGuidedInjuryFields = buildGuidedInjuryFields(nextGuidedInjuries, {
      noRestrictions: nextNoRestrictions,
    });
    setNoRestrictions(nextNoRestrictions);
    setGuidedInjuries(nextGuidedInjuries);
    setForm((currentForm) => ({
      ...currentForm,
      ...nextGuidedInjuryFields,
    }));
  }

  function updateAthlete<K extends keyof PlanRequest["athlete"]>(key: K, value: PlanRequest["athlete"][K]) {
    setForm((current) => ({
      ...current,
      athlete: {
        ...current.athlete,
        [key]: value,
      },
    }));
  }

  function updateField<K extends keyof PlanRequest>(key: K, value: PlanRequest[K]) {
    setForm((current) => ({
      ...current,
      [key]: value,
    }));
  }

  function updateRoundsField(key: "roundCount" | "roundDuration", value: string) {
    const parsed = parseRoundsFormat(form.rounds_format);
    const nextRounds = key === "roundCount"
      ? buildRoundsFormat(value, parsed.roundDuration)
      : buildRoundsFormat(parsed.roundCount, value);
    updateField("rounds_format", nextRounds);
  }

  function updateGuidedInjury<K extends keyof GuidedInjuryState>(index: number, key: K, value: GuidedInjuryState[K]) {
    setGuidedInjuries((currentGuidedInjuries) => {
      const nextGuidedInjuries = [...currentGuidedInjuries];
      nextGuidedInjuries[index] = coerceGuidedInjuryEditState({
        ...(nextGuidedInjuries[index] ?? EMPTY_GUIDED_INJURY),
        [key]: value,
      });

      const nextGuidedInjuryFields = buildGuidedInjuryFields(nextGuidedInjuries, {
        noRestrictions: false,
      });

      setNoRestrictions(false);
      setForm((currentForm) => ({
        ...currentForm,
        ...nextGuidedInjuryFields,
      }));

      return nextGuidedInjuries;
    });
  }

  function handleEditGuidedInjury(index: number) {
    setActiveGuidedInjuryIndex(index);
  }

  function handleNoRestrictionsChange(checked: boolean) {
    if (!checked) {
      setShowClearInjuriesConfirm(false);
      const nextGuidedInjuries = guidedInjuries.length ? guidedInjuries : [{ ...EMPTY_GUIDED_INJURY }];
      syncGuidedInjuryFields(nextGuidedInjuries, false);
      setActiveGuidedInjuryIndex(nextGuidedInjuries.length - 1);
      return;
    }
    if (guidedInjuries.length > 0) {
      setShowClearInjuriesConfirm(true);
      return;
    }
    syncGuidedInjuryFields([], true);
    setActiveGuidedInjuryIndex(null);
  }

  function handleAddGuidedInjury() {
    const nextGuidedInjuries = [...guidedInjuries, { ...EMPTY_GUIDED_INJURY }];
    syncGuidedInjuryFields(nextGuidedInjuries, false);
    setActiveGuidedInjuryIndex(nextGuidedInjuries.length - 1);
  }

  function handleConfirmClearInjuries() {
    setShowClearInjuriesConfirm(false);
    syncGuidedInjuryFields([], true);
    setActiveGuidedInjuryIndex(null);
  }

  function handleBodyMapZoneSelect(zoneKey: string, label: string) {
    // Match by the stable zone key first; fall back to a legacy injury whose
    // typed area still equals the zone label and has no zone key yet.
    const existingIndex = guidedInjuries.findIndex(
      (injury) =>
        (injury.zone && injury.zone === zoneKey) ||
        (!injury.zone && injury.area.trim().toLowerCase() === label.toLowerCase()),
    );
    if (existingIndex >= 0) {
      // The zone is already marked — cycle its severity (low → moderate → high)
      // so the legend is usable straight from the map, never removing it or
      // creating a duplicate. Backfill the zone key on legacy matches so the
      // zone stays lit even after the athlete rewrites the free-text area.
      const existing = guidedInjuries[existingIndex];
      const nextGuidedInjuries = [...guidedInjuries];
      nextGuidedInjuries[existingIndex] = coerceGuidedInjuryEditState({
        ...existing,
        severity: cycleGuidedInjurySeverity(existing.severity),
        zone: existing.zone || zoneKey,
      });
      syncGuidedInjuryFields(nextGuidedInjuries, false);
      // Surface the affected card so its severity chips track the change.
      setActiveGuidedInjuryIndex(existingIndex);
      return;
    }

    const emptyIndex = guidedInjuries.findIndex((injury) => !injury.area.trim() && !injury.zone);
    if (emptyIndex >= 0) {
      const nextGuidedInjuries = [...guidedInjuries];
      nextGuidedInjuries[emptyIndex] = coerceGuidedInjuryEditState({
        ...nextGuidedInjuries[emptyIndex],
        area: label,
        zone: zoneKey,
      });
      syncGuidedInjuryFields(nextGuidedInjuries, false);
      setActiveGuidedInjuryIndex(emptyIndex);
      return;
    }

    const nextGuidedInjuries = [...guidedInjuries, { ...EMPTY_GUIDED_INJURY, area: label, zone: zoneKey }];
    syncGuidedInjuryFields(nextGuidedInjuries, false);
    setActiveGuidedInjuryIndex(nextGuidedInjuries.length - 1);
  }

  // Removal now only happens from a card's × button. Guard it with the existing
  // confirm panel when the injury carries detail beyond its area/zone, so a
  // single tap can't silently discard filled-in safety answers.
  function handleRequestRemoveGuidedInjury(index: number) {
    const injury = guidedInjuries[index];
    if (injury && hasGuidedInjuryContent({ ...injury, area: "", zone: "" })) {
      setPendingInjuryRemovalIndex(index);
      return;
    }
    handleRemoveGuidedInjury(index);
  }

  function handleConfirmRemovePendingInjury() {
    if (pendingInjuryRemovalIndex === null) {
      return;
    }
    handleRemoveGuidedInjury(pendingInjuryRemovalIndex);
    setPendingInjuryRemovalIndex(null);
  }

  function handleCancelRemovePendingInjury() {
    setPendingInjuryRemovalIndex(null);
  }

  function handleRemoveGuidedInjury(index: number) {
    const nextGuidedInjuries = guidedInjuries.filter((_, currentIndex) => currentIndex !== index);
    if (!nextGuidedInjuries.length) {
      syncGuidedInjuryFields([], true);
      setActiveGuidedInjuryIndex(null);
      return;
    }

    syncGuidedInjuryFields(nextGuidedInjuries, false);
    setActiveGuidedInjuryIndex((currentIndex) => {
      if (currentIndex === null) {
        return null;
      }
      if (currentIndex === index) {
        return Math.min(index, nextGuidedInjuries.length - 1);
      }
      return currentIndex > index ? currentIndex - 1 : currentIndex;
    });
  }

  function toggleFieldValue(
    key: "training_availability" | "equipment_access" | "key_goals" | "weak_areas" | "hard_sparring_days" | "support_work_days",
    value: string,
  ) {
    setForm((current) => {
      const currentValues = key === "equipment_access"
        ? retainKnownOptionValues(current[key], EQUIPMENT_ACCESS_OPTIONS)
        : current[key];
      const alreadySelected = currentValues.includes(value);
      const performanceFocusGroup = getPerformanceFocusGroupForField(key);
      const performanceFocusCap = performanceFocusGroup
        ? getPerformanceFocusCap(current.fight_date, { timeZone: current.athlete.athlete_timezone })
        : null;
      const totalSelectedPerformanceFocus = current.key_goals.length + current.weak_areas.length;
      const currentDaysOutCtx = buildDaysOutContext(computeDaysUntilFight(current.fight_date), {
        hasHardSparring: current.hard_sparring_days.length > 0,
      });

      if (
        performanceFocusGroup
        && !alreadySelected
        && !getPerformanceFocusOptionAvailability(currentDaysOutCtx, performanceFocusGroup, value).available
      ) {
        return current;
      }

      if (performanceFocusGroup && !alreadySelected && performanceFocusCap && totalSelectedPerformanceFocus >= performanceFocusCap.maxSelections) {
        return current;
      }
      if (key === "weak_areas" && !alreadySelected && current.weak_areas.length >= 2) {
        return current;
      }

      const nextValues = toggleListValue(currentValues, value);

      // When a training-availability day is unchecked, also strip it from the
      // hard sparring / Light Combat pickers so stale picks don't trigger the
      // sparring-consistency hard error.
      if (key === "training_availability" && alreadySelected) {
        return {
          ...current,
          training_availability: nextValues,
          hard_sparring_days: current.hard_sparring_days.filter((day) => day !== value),
          support_work_days: current.support_work_days.filter((day) => day !== value),
        };
      }

      return {
        ...current,
        [key]: nextValues,
      };
    });
  }

  function shouldEvaluateTrainingGate(action: TrainingGateAction, targetStep?: number): boolean {
    if (action === "generate") {
      return true;
    }

    if (action === "save_draft") {
      return currentStep === 2;
    }

    if (action === "next") {
      return currentStep >= 2;
    }

    return targetStep !== undefined && targetStep > currentStep && targetStep > 2;
  }

  function getTrainingGateDecision(
    nextForm: PlanRequest,
    action: TrainingGateAction,
    targetStep?: number,
  ): TrainingGateDecision {
    if (!shouldEvaluateTrainingGate(action, targetStep)) {
      return { kind: "allow" };
    }

    const availabilityConsistency = getAvailabilityConsistency(
      nextForm.training_availability,
      nextForm.weekly_training_frequency,
    );
    if (availabilityConsistency.hardError) {
      return {
        kind: "hard_error",
        source: "availability",
        message: `${availabilityConsistency.hardError} Reduce sessions or add more available days.`,
      };
    }

    const sparringConsistency = getSparringConsistency(
      nextForm.training_availability,
      nextForm.hard_sparring_days,
      nextForm.support_work_days,
      action !== "save_draft" && nextForm.no_scheduled_fight !== true,
    );
    if (sparringConsistency.hardError) {
      return {
        kind: "hard_error",
        source: "sparring",
        message: sparringConsistency.hardError,
      };
    }

    const hardSparringWarning = getHardSparringWarning(
      nextForm.hard_sparring_days,
      nextForm.weekly_training_frequency,
    );
    const hardSparringWarningAcknowledged =
      acknowledgedHardSparringWarningKey === hardSparringWarning.acknowledgementContextKey;

    if (action !== "save_draft" && hardSparringWarning.requiresAcknowledgement && !hardSparringWarningAcknowledged) {
      return {
        kind: "warning_ack_required",
        message:
          action === "generate"
            ? "Acknowledge the hard sparring warning in the Training step before generating."
            : "Acknowledge the hard sparring warning in the Training step before continuing.",
        shouldRedirectToTraining: action === "generate" || currentStep > 2 || (targetStep !== undefined && targetStep > 2),
      };
    }

    return { kind: "allow" };
  }

  function applyTrainingGate(nextForm: PlanRequest, action: TrainingGateAction, targetStep?: number): boolean {
    const decision = getTrainingGateDecision(nextForm, action, targetStep);
    if (decision.kind === "allow") {
      return true;
    }

    if (decision.kind === "warning_ack_required") {
      return reportInvalidField({
        message: decision.message,
        fieldId: "hardSparringAck",
        step: currentStep !== 2 ? 2 : undefined,
      });
    }

    // hard_error from training gate covers availability/sparring consistency on the Training step.
    // Route to the panel that actually surfaces the failing check.
    const hardErrorFieldId = decision.source === "sparring"
      ? "sparringConsistencyAlert"
      : "availabilityConsistencyAlert";
    return reportInvalidField({
      message: decision.message,
      fieldId: hardErrorFieldId,
      step: currentStep !== 2 ? 2 : undefined,
    });
  }

  function reportInvalidField(args: { message: string; fieldId: string; step?: number }): false {
    const { message, fieldId } = args;
    // Fall back to the field's home step so an invalid target on a different
    // step is never silently dropped when the caller omits `step`.
    const targetStep = args.step ?? resolveFieldStep(fieldId);
    setError(message);
    setInvalidFieldId(fieldId);
    // The nonce guarantees the focus effect re-fires even when validation
    // hits the same field twice in a row (e.g. user re-clicks Continue).
    setValidationFocusRequest({ fieldId, nonce: Date.now() });
    if (targetStep !== undefined && targetStep !== currentStep) {
      setCurrentStep(targetStep);
      setIsMobileProgressOpen(true);
    }
    return false;
  }

  function validateCurrentStep(
    nextForm: PlanRequest,
    action: TrainingGateAction = "next",
    targetStep?: number,
  ): boolean {
    if (currentStep === 0) {
      if (!isValidRecordFormat(nextForm.athlete.record ?? "")) {
        return reportInvalidField({
          message: "Record must use x-x or x-x-x format, like 5-1 or 12-2-1.",
          fieldId: "record",
        });
      }
      if (!nextForm.athlete.technical_style.length) {
        return reportInvalidField({
          message: "Select a combat sport before continuing.",
          fieldId: "technicalStyle",
        });
      }
    }
    if (currentStep === 1) {
      if (!nextForm.fight_date && !noScheduledFight) {
        return reportInvalidField({
          message: "Choose your fight date or mark \"No scheduled fight\" before continuing.",
          fieldId: "fightDate",
        });
      }
      if (!noScheduledFight && isFightDateInPast(nextForm.fight_date)) {
        return reportInvalidField({
          message: FIGHT_DATE_IN_PAST_MESSAGE,
          fieldId: "fightDate",
        });
      }
      const parsedRounds = parseRoundsFormat(nextForm.rounds_format);
      if (!parsedRounds.roundCount) {
        return reportInvalidField({
          message: "Choose both round count and round duration before continuing.",
          fieldId: "roundCount",
        });
      }
      if (!parsedRounds.roundDuration) {
        return reportInvalidField({
          message: "Choose both round count and round duration before continuing.",
          fieldId: "roundDuration",
        });
      }
    }
    if (currentStep === 2 && !nextForm.training_availability.length) {
      return reportInvalidField({
        message: "Pick at least one training availability day before continuing.",
        fieldId: "trainingAvailabilityGroup",
      });
    }
    if (currentStep === 3 && (nextForm.guided_injuries ?? []).some((injury) => hasGuidedInjuryDescriptorWithoutArea(injury))) {
      const invalidIndex = (nextForm.guided_injuries ?? []).findIndex((injury) => hasGuidedInjuryDescriptorWithoutArea(injury));
      return reportInvalidField({
        message: "Add a pain area or body part before choosing severity or trend.",
        fieldId: invalidIndex >= 0 ? `guidedInjuryCard-${invalidIndex}` : "guidedInjuriesSection",
      });
    }
    if (currentStep === 3 && !noRestrictions) {
      const hasMeaningfulDetail = guidedInjuries.some(
        (injury) => Boolean(injury.injury_type) || Boolean(injury.notes.trim()),
      );
      if (!hasMeaningfulDetail) {
        const targetIndex = guidedInjuries.findIndex(
          (injury) => !injury.injury_type && !injury.notes.trim(),
        );
        return reportInvalidField({
          message: "Add an injury type or describe the injury, or tick \"No current injuries or restrictions\" to continue.",
          fieldId: targetIndex >= 0 ? `guidedInjuryCard-${targetIndex}` : "guidedInjuryCard-0",
        });
      }
    }
    if (currentStep === PERFORMANCE_STEP_INDEX) {
      const focusValidation = validatePerformanceFocusSelections(
        nextForm.fight_date,
        { keyGoals: nextForm.key_goals, weakAreas: nextForm.weak_areas },
        { timeZone: nextForm.athlete.athlete_timezone },
      );
      if (focusValidation.isOverCap) {
        return reportInvalidField({
          message: focusValidation.errorMessage ?? "Goals and weak areas exceed the current cap. Update your selections before continuing.",
          fieldId: "keyGoalsGroup",
        });
      }
    }
    return applyTrainingGate(nextForm, action, targetStep);
  }

  function validateForGeneration(nextForm: PlanRequest): boolean {
    if (!validateCurrentStep(nextForm, "generate")) {
      return false;
    }
    if (!nextForm.athlete.technical_style.length) {
      return reportInvalidField({
        message: "Select a combat sport before generating your plan.",
        fieldId: "technicalStyle",
        step: 0,
      });
    }
    if (!nextForm.fight_date && !noScheduledFight) {
      return reportInvalidField({
        message: "Choose your fight date or mark \"No scheduled fight\" before generating your plan.",
        fieldId: "fightDate",
        step: 1,
      });
    }
    if (!noScheduledFight && isFightDateInPast(nextForm.fight_date)) {
      return reportInvalidField({
        message: FIGHT_DATE_IN_PAST_MESSAGE,
        fieldId: "fightDate",
        step: 1,
      });
    }
    if (!nextForm.training_availability.length) {
      return reportInvalidField({
        message: "Pick at least one training availability option before generating your plan.",
        fieldId: "trainingAvailabilityGroup",
        step: 2,
      });
    }
    if (!nextForm.weekly_training_frequency || nextForm.weekly_training_frequency < 1) {
      return reportInvalidField({
        message: "Planned sessions per week must be at least 1.",
        fieldId: "sessionsPerWeek",
        step: 1,
      });
    }
    if (nextForm.weekly_training_frequency > 6) {
      return reportInvalidField({
        message: "Planned sessions per week cannot exceed 6.",
        fieldId: "sessionsPerWeek",
        step: 1,
      });
    }
    const parsedRounds = parseRoundsFormat(nextForm.rounds_format);
    if (!parsedRounds.roundCount) {
      return reportInvalidField({
        message: "Choose both round count and round duration before generating your plan.",
        fieldId: "roundCount",
        step: 1,
      });
    }
    if (!parsedRounds.roundDuration) {
      return reportInvalidField({
        message: "Choose both round count and round duration before generating your plan.",
        fieldId: "roundDuration",
        step: 1,
      });
    }
    const focusValidation = validatePerformanceFocusSelections(
      nextForm.fight_date,
      {
        keyGoals: nextForm.key_goals,
        weakAreas: nextForm.weak_areas,
      },
      {
        timeZone: nextForm.athlete.athlete_timezone,
      },
    );
    if (focusValidation.isOverCap) {
      return reportInvalidField({
        message: focusValidation.errorMessage ?? "Goals and weak areas exceed the current cap. Update your selections before continuing.",
        fieldId: "keyGoalsGroup",
        step: PERFORMANCE_STEP_INDEX,
      });
    }
    return true;
  }

  async function persistDraft(step = currentStep, snapshot?: PlanRequest) {
    if (!session?.access_token) {
      return;
    }
    const nextForm = snapshot ?? buildFormSnapshot();
    setForm(nextForm);
    setSaveStatus("saving");
    try {
      const nextDraft = {
        ...mergePlanRequestDraft(me?.profile.onboarding_draft as Record<string, unknown> | null | undefined, nextForm, step),
        ...nextForm,
        current_step: step,
        no_scheduled_fight: noScheduledFight,
      };
      await saveOnboardingDraft(session.access_token, {
        full_name: nextForm.athlete.full_name,
        technical_style: nextForm.athlete.technical_style,
        tactical_style: nextForm.athlete.tactical_style,
        stance: nextForm.athlete.stance,
        professional_status: nextForm.athlete.professional_status,
        record: nextForm.athlete.record,
        athlete_timezone: nextForm.athlete.athlete_timezone,
        onboarding_draft: nextDraft,
      });

      const nextMe = mergeSavedOnboardingDraft(me, nextDraft, nextForm.athlete);
      if (nextMe) {
        replaceMe(nextMe);
      }
      lastSavedSnapshotRef.current = JSON.stringify(nextForm);
      setSaveStatus("saved");
      setLastSavedAt(Date.now());
    } catch (persistError) {
      setSaveStatus("error");
      throw persistError;
    }
  }

  function handleSaveDraft() {
    setMessage(null);
    setError(null);
    setInvalidFieldId(null);
    startTransition(async () => {
      const nextForm = buildFormSnapshot();
      if (!validateCurrentStep(nextForm, "save_draft")) {
        return;
      }
      if (!session?.access_token) {
        setError(appText("text_4b5fdd19a96c"));
        return;
      }
      try {
        await persistDraft();
        setMessage(appText("text_be997844b2a8"));
      } catch (draftError) {
        setError(draftError instanceof Error ? draftError.message : appText("text_0b53da598881"));
      }
    });
  }

  function handleNext() {
    const nextStep = Math.min(currentStep + 1, steps.length - 1);
    setMessage(null);
    setError(null);
    setInvalidFieldId(null);
    startTransition(async () => {
      const nextForm = buildFormSnapshot();
      if (!validateCurrentStep(nextForm, "next", nextStep)) {
        return;
      }
      setCurrentStep(nextStep);
      setIsMobileProgressOpen(false);
      try {
        await persistDraft(nextStep);
      } catch {
        // Draft persistence is best-effort; navigation has already advanced.
      }
    });
  }

  function handleBack() {
    setError(null);
    setInvalidFieldId(null);
    setCurrentStep((step) => Math.max(step - 1, 0));
    setIsMobileProgressOpen(false);
  }

  function handleStepSelect(targetStep: number) {
    setMessage(null);
    setError(null);
    setInvalidFieldId(null);
    let nextForm: PlanRequest | null = null;
    function getNextForm() {
      nextForm ??= buildFormSnapshot();
      return nextForm;
    }
    if (targetStep === steps.length - 1 && targetStep > currentStep) {
      const reviewIssue = getReviewStepBlockingIssue(getNextForm(), {
        hardSparringWarningLocked,
        noScheduledFight,
      });
      if (reviewIssue) {
        reportInvalidField({
          message: reviewIssue.message,
          fieldId: reviewIssue.fieldId,
          step: reviewIssue.step,
        });
        return;
      }
    }
    if (!canSelectWizardStep({
      currentStep,
      targetStep,
      lastSelectableStep: steps.length,
      validateCurrentStep: () => validateCurrentStep(getNextForm(), "step_select", targetStep),
    })) {
      return;
    }
    setCurrentStep(targetStep);
    setIsMobileProgressOpen(false);

    if (!session?.access_token || !isValidRecordFormat(getNextForm().athlete.record ?? "")) {
      return;
    }

    startTransition(async () => {
      try {
        await persistDraft(targetStep);
      } catch {
        // Keep jump navigation responsive even if background draft persistence fails.
      }
    });
  }

  function handleGenerate() {
    setMessage(null);
    setError(null);
    setInvalidFieldId(null);
    startTransition(async () => {
      const nextForm = buildFormSnapshot();
      if (!validateForGeneration(nextForm)) {
        return;
      }
      if (!session?.access_token) {
        setError(appText("text_b5a7aec99051"));
        return;
      }
      try {
        await persistDraft(steps.length - 1, nextForm);
        if (!writePendingGenerationPayload(nextForm, "self_serve")) {
          setError(appText("text_083352324ed7"));
          return;
        }
        markGenerationIntent();
        router.push("/generate");
      } catch (draftError) {
        setError(draftError instanceof Error ? draftError.message : appText("text_61a074c4218b"));
      }
    });
  }

  const technicalStyleLabel = getOptionLabel(TECHNICAL_STYLE_OPTIONS, form.athlete.technical_style[0] ?? "") || "Not provided";
  const tacticalStyleLabel = getOptionLabel(TACTICAL_STYLE_OPTIONS, form.athlete.tactical_style[0] ?? "") || "Not provided";
  const statusLabel = getOptionLabel(PROFESSIONAL_STATUS_OPTIONS, form.athlete.professional_status ?? "") || "Not provided";
  const stanceLabel = getOptionLabel(STANCE_OPTIONS, form.athlete.stance ?? "") || "Not provided";
  const parsedRounds = parseRoundsFormat(form.rounds_format);
  const availabilityConsistency = getAvailabilityConsistency(
    form.training_availability,
    form.weekly_training_frequency,
  );
  const selectedTrainingAvailabilityLabels = getOptionLabels(TRAINING_AVAILABILITY_OPTIONS, form.training_availability);
  const selectedEquipmentAccessLabels = getOptionLabels(EQUIPMENT_ACCESS_OPTIONS, form.equipment_access);
  const selectedHardSparringLabels = getOptionLabels(TRAINING_AVAILABILITY_OPTIONS, form.hard_sparring_days);
  const selectedSupportWorkLabels = getOptionLabels(TRAINING_AVAILABILITY_OPTIONS, form.support_work_days);
  const selectedGoalLabels = getOptionLabels(KEY_GOAL_OPTIONS, form.key_goals);
  const selectedWeakAreaLabels = getOptionLabels(WEAK_AREA_OPTIONS, form.weak_areas);
  const goalWeakAreaOverlaps = getGoalWeakAreaOverlaps(form.key_goals, form.weak_areas);
  const primaryOverlap = goalWeakAreaOverlaps[0] ?? null;
  const overlapClarificationPrompt = goalWeakAreaOverlaps.length > 1
    ? "You selected multiple qualities as both goals and weak areas. Clarify each one if useful."
    : primaryOverlap
      ? `You selected ${primaryOverlap.label} as both a goal and a weak area. What does that mean?`
      : "";
  const overlapReviewLabel = goalWeakAreaOverlaps.length > 1 ? "Multiple qualities" : goalWeakAreaOverlaps[0]?.label ?? "";
  const primaryGoalLabel = getOptionLabel(KEY_GOAL_OPTIONS, form.primary_goal ?? "") || "Not selected";
  const primaryWeakAreaLabel = getOptionLabel(WEAK_AREA_OPTIONS, form.primary_weak_area ?? "") || "Not selected";
  const secondaryGoalLabels = getOptionLabels(KEY_GOAL_OPTIONS, form.key_goals.filter((goal) => goal !== form.primary_goal));
  const secondaryWeakAreaLabels = getOptionLabels(WEAK_AREA_OPTIONS, form.weak_areas.filter((area) => area !== form.primary_weak_area));
  const performanceFocusCap = getPerformanceFocusCap(form.fight_date, {
    timeZone: form.athlete.athlete_timezone,
  });
  const selectedPerformanceFocusCount = performanceFocusValidation.totalSelections;
  const performanceFocusCapValue = performanceFocusCap?.maxSelections ?? null;
  const performanceFocusCapReached = performanceFocusCapValue !== null && selectedPerformanceFocusCount >= performanceFocusCapValue;
  const performanceFocusCapExceeded = performanceFocusValidation.isOverCap;
  const getKeyGoalDisabledReason = (option: IntakeOption) => {
    const availability = getPerformanceFocusOptionAvailability(daysOutCtx, "key_goals", option.value);
    return availability.available ? null : availability.reason ?? "Too close to fight day.";
  };
  const getWeakAreaDisabledReason = (option: IntakeOption) => {
    const availability = getPerformanceFocusOptionAvailability(daysOutCtx, "weak_areas", option.value);
    return availability.available ? null : availability.reason ?? "Too close to fight day.";
  };
  const remainingPerformanceFocusSelections = performanceFocusCapValue === null
    ? null
    : Math.max(performanceFocusCapValue - selectedPerformanceFocusCount, 0);
  const performanceFocusWindowLabel = performanceFocusCap?.windowLabel.toLowerCase() ?? "this camp window";
  const performanceFocusReason = performanceFocusCap?.reason ?? "";
  const selectedTrainingAvailability = formatJoinedLabels(selectedTrainingAvailabilityLabels, "No availability selected");
  const selectedEquipmentAccess = formatJoinedLabels(selectedEquipmentAccessLabels, "No equipment selected");
  const selectedHardSparring = formatJoinedLabels(selectedHardSparringLabels, "No fixed hard sparring days");
  const selectedSupportWorkDays = formatJoinedLabels(selectedSupportWorkLabels, "No Light Combat days selected");
  const fightDayLockReason = `Fight day — ${formatFightDateValue(form.fight_date)}`;
  const selectedGoals = formatJoinedLabels(selectedGoalLabels, "No goals selected");
  const selectedWeakAreas = formatJoinedLabels(selectedWeakAreaLabels, "No weak areas selected");
  const performanceFocusCapTitle = performanceFocusCapValue === null
    ? "Set a fight date to calculate your focus cap"
    : `${selectedPerformanceFocusCount} of ${performanceFocusCapValue} focus picks used`;
  const performanceFocusCapBadge = performanceFocusCapValue === null
    ? "—/—"
    : `${selectedPerformanceFocusCount}/${performanceFocusCapValue}`;
  const performanceFocusCapDetail = performanceFocusCapValue === null
    ? "Goals and weak areas share a cap once the fight date is set so the plan can match the camp window."
    : performanceFocusCapExceeded
      ? `Goals and weak areas share this ${performanceFocusCapValue}-pick cap for ${performanceFocusWindowLabel}. ${performanceFocusReason} You are ${selectedPerformanceFocusCount - performanceFocusCapValue} over the current cap, so unselect to get back within it.`
      : performanceFocusCapReached
        ? `Goals and weak areas share this ${performanceFocusCapValue}-pick cap for ${performanceFocusWindowLabel}. ${performanceFocusReason} Cap reached. Unselect one to change your focus.`
        : `Goals and weak areas share this ${performanceFocusCapValue}-pick cap for ${performanceFocusWindowLabel}. ${performanceFocusReason} You can add ${remainingPerformanceFocusSelections} more.`;
  const performanceFocusCapHint = performanceFocusCapValue === null
    ? "Set the fight date to lock in your focus cap."
    : performanceFocusCapExceeded
      ? `${selectedPerformanceFocusCount - performanceFocusCapValue} over cap — unselect to fit.`
      : performanceFocusCapReached
        ? "Cap reached. Unselect one to swap."
        : remainingPerformanceFocusSelections === 1
          ? "1 pick remaining."
          : `${remainingPerformanceFocusSelections} picks remaining.`;
  const keyGoalCapDisabledReason = performanceFocusCapReached ? FOCUS_CAP_DISABLED_REASON : undefined;
  const weakAreaCapDisabledReason = form.weak_areas.length >= 2
    ? "Maximum of 2 weak areas reached. Unselect one to add another."
    : performanceFocusCapReached
      ? FOCUS_CAP_DISABLED_REASON
      : undefined;
  // A draft written before target-weight suppression can still carry one, so
  // the derived cut status and the review row are suppressed for a minor too —
  // otherwise a hidden field would keep surfacing through the summaries.
  const weightCutStatus = isMinorAthlete
    ? null
    : formatWeightCutStatus(form.athlete.weight_kg, form.athlete.target_weight_kg);
  const equipmentLimitations = formatEquipmentLimitations(form.equipment_access);
  const sparringConsistency = getSparringConsistency(
    form.training_availability,
    form.hard_sparring_days,
    form.support_work_days,
    !noScheduledFight,
  );
  const hardSparringWarning = getHardSparringWarning(
    form.hard_sparring_days,
    form.weekly_training_frequency,
  );
  const hardSparringWarningAcknowledged =
    acknowledgedHardSparringWarningKey === hardSparringWarning.acknowledgementContextKey;
  const hardSparringWarningLocked =
    hardSparringWarning.requiresAcknowledgement && !hardSparringWarningAcknowledged;
  const trainingPreferenceText = (form.training_preference || "").trim();
  const mindsetChallengesText = (form.mindset_challenges || "").trim();
  const notesText = (form.notes || "").trim();
  const sparringCollisionRisk = formatSparringCollisionRisk({
    fatigueLevel: form.fatigue_level || "low",
    injuries: form.injuries || "",
    sessionsPerWeek: form.weekly_training_frequency,
    technicalStyle: form.athlete.technical_style[0] ?? "",
    hardSparringDays: selectedHardSparringLabels,
  });
  const highFatigueFlag = (form.fatigue_level || "low") === "high" ? "High fatigue already reported" : null;
  const hasExtraPerformanceNotes = Boolean(mindsetChallengesText || notesText);
  const hasTrainingPreference = Boolean(trainingPreferenceText);
  const restrictionSummary = formatRestrictionSummary(form.injuries);
  const sexLabel = form.athlete.sex
    ? SEX_OPTIONS.find((option) => option.value === form.athlete.sex)?.label ?? formatValue(form.athlete.sex)
    : "Not provided";
  const profileReviewItems = [
    { label: "Name", value: formatValue(form.athlete.full_name) },
    ...(hasValue(form.athlete.sex) ? [{ label: "Sex", value: sexLabel }] : []),
    ...(hasValue(form.athlete.age) ? [{ label: "Age", value: formatValue(form.athlete.age) }] : []),
    ...(hasValue(form.athlete.height_cm) ? [{ label: "Height", value: `${form.athlete.height_cm} cm` }] : []),
    ...(hasValue(form.athlete.weight_kg) ? [{ label: "Current weight", value: `${form.athlete.weight_kg} kg` }] : []),
    ...(!isMinorAthlete && hasValue(form.athlete.target_weight_kg)
      ? [{ label: "Target weight", value: `${form.athlete.target_weight_kg} kg` }]
      : []),
    { label: "Stance", value: stanceLabel },
    { label: "Combat sport", value: technicalStyleLabel },
    { label: "Tactical style", value: tacticalStyleLabel },
    { label: "Professional status", value: statusLabel },
    { label: "Record", value: formatValue(form.athlete.record) },
  ];
  const campSetupReviewItems = [
    { label: "Fight date", value: formatFightDateValue(form.fight_date) },
    { label: "Rounds", value: formatValue(form.rounds_format) },
    { label: "Planned sessions per week", value: formatValue(form.weekly_training_frequency) },
    { label: "Fatigue level", value: formatValue(form.fatigue_level || "low") },
  ];
  const trainingReviewItems = [
    { label: "Training availability", value: selectedTrainingAvailability },
    { label: "Hard sparring days", value: selectedHardSparring },
    { label: "Light Combat days", value: selectedSupportWorkDays },
    { label: "Equipment access", value: selectedEquipmentAccess },
    ...(availabilityConsistency.hardError
      ? [{ label: "Schedule issue", value: availabilityConsistency.hardError }]
      : availabilityConsistency.softWarning
        ? [{ label: "Schedule note", value: availabilityConsistency.softWarning }]
        : []),
    ...(sparringConsistency.hardError
      ? [{ label: "Sparring schedule issue", value: sparringConsistency.hardError }]
      : sparringConsistency.softWarning
        ? [{ label: "Sparring schedule note", value: sparringConsistency.softWarning }]
        : []),
    ...(hardSparringWarning.message
      ? [{
          label: "Hard sparring load",
          value: hardSparringWarning.message,
        }]
      : []),
    {
      label: "Session preference",
      value: hasTrainingPreference ? trainingPreferenceText : "No session preference provided.",
    },
  ];
  const constraintsReviewItems = [
    { label: "Injuries / pain areas", value: restrictionSummary },
    ...(weightCutStatus ? [{ label: "Weight-cut status", value: weightCutStatus }] : []),
    ...(highFatigueFlag ? [{ label: "Fatigue flag", value: highFatigueFlag }] : []),
    ...(equipmentLimitations ? [{ label: "Equipment limitations", value: equipmentLimitations }] : []),
    ...(sparringCollisionRisk ? [{ label: "Sparring collision risk", value: sparringCollisionRisk }] : []),
  ];
  const performanceReviewItems = [
    { label: "Goals - Primary", value: primaryGoalLabel },
    { label: "Goals - Secondary", value: formatJoinedLabels(secondaryGoalLabels, "None") },
    { label: "Weak areas - Primary", value: primaryWeakAreaLabel },
    { label: "Weak areas - Secondary", value: formatJoinedLabels(secondaryWeakAreaLabels, "None") },
    ...(form.goal_weakness_collision_detail?.trim()
      ? [{
          label: "Priority clarification",
          value: `${overlapReviewLabel} - ${form.goal_weakness_collision_detail.trim()}`,
        }]
      : []),
    ...(mindsetChallengesText ? [{ label: "Mental / confidence issue", value: mindsetChallengesText }] : []),
    ...(notesText ? [{ label: "Anything else we should know?", value: notesText }] : []),
    ...(!hasExtraPerformanceNotes ? [{ label: "Extra context", value: "No extra context provided." }] : []),
  ];
  const reviewChecklistItems: StepValidationCheck[] = [
    {
      label: form.athlete.technical_style.length ? "Combat sport is selected." : "Combat sport must be selected before generation.",
      status: form.athlete.technical_style.length ? "done" : "pending",
    },
    {
      label: form.fight_date
        ? "Fight date is set."
        : noScheduledFight
          ? "No scheduled fight (open camp)."
          : "Fight date must be set before generation.",
      status: form.fight_date || noScheduledFight ? "done" : "pending",
    },
    {
      label: form.training_availability.length
        ? "Training availability is saved."
        : "Training availability needs at least one selected option.",
      status: form.training_availability.length ? "done" : "pending",
    },
    {
      label:
        form.weekly_training_frequency && form.weekly_training_frequency >= 1 && form.weekly_training_frequency <= 6
          ? "Planned sessions per week are in range."
          : "Planned sessions per week must stay between 1 and 6.",
      status:
        form.weekly_training_frequency && form.weekly_training_frequency >= 1 && form.weekly_training_frequency <= 6
          ? "done"
          : "pending",
    },
    {
      label:
        parsedRounds.roundCount && parsedRounds.roundDuration
          ? "Round count and duration are complete."
          : "Choose both round count and round duration before generation.",
      status: parsedRounds.roundCount && parsedRounds.roundDuration ? "done" : "pending",
    },
    ...(availabilityConsistency.hardError
      ? [{ label: availabilityConsistency.hardError, status: "warning" as const }]
      : [{ label: "Training availability can support the selected session count.", status: "done" as const }]),
    ...(sparringConsistency.hardError
      ? [{ label: sparringConsistency.hardError, status: "warning" as const }]
      : [{ label: "Hard sparring and support days fit the current availability.", status: "done" as const }]),
    ...(hardSparringWarning.message
      ? [{
          label: hardSparringWarningAcknowledged
            ? `${hardSparringWarning.message} Acknowledged in Training.`
            : `${hardSparringWarning.message} Return to Training to acknowledge it.`,
          status: hardSparringWarningAcknowledged ? "done" : "warning",
        } as const]
      : []),
  ];
  const currentStepValidation = (() => {
    switch (currentStep) {
      case 0:
        return {
          title: "Profile essentials",
          description: "Save the athlete identity fields that power the rest of the intake.",
          checks: [
            {
              label: form.athlete.full_name.trim() ? "Full name is saved." : "Add the athlete's full name.",
              status: form.athlete.full_name.trim() ? "done" : "pending",
            },
            {
              label: recordHasError ? "Record must use x-x or x-x-x format." : "Record format is valid.",
              status: recordHasError ? "pending" : "done",
            },
            {
              label: form.athlete.technical_style.length ? "Combat sport is selected." : "Select a combat sport.",
              status: form.athlete.technical_style.length ? "done" : "pending",
            },
          ] satisfies StepValidationCheck[],
        };
      case 1:
        return {
          title: "Camp setup",
          description: "Lock in the timing and round structure so the plan can scale to the fight window.",
          checks: [
            {
              label: form.fight_date
                ? "Fight date is set."
                : noScheduledFight
                  ? "No scheduled fight selected. Open camp."
                  : "Choose the fight date or select No scheduled fight.",
              status: form.fight_date || noScheduledFight ? "done" : "pending",
            },
            {
              label:
                parsedRounds.roundCount && parsedRounds.roundDuration
                  ? "Round count and duration are complete."
                  : "Choose both round count and round duration.",
              status: parsedRounds.roundCount && parsedRounds.roundDuration ? "done" : "pending",
            },
            {
              label:
                form.weekly_training_frequency && form.weekly_training_frequency >= 1 && form.weekly_training_frequency <= 6
                  ? "Planned sessions per week are in range."
                  : "Keep planned sessions per week between 1 and 6.",
              status:
                form.weekly_training_frequency && form.weekly_training_frequency >= 1 && form.weekly_training_frequency <= 6
                  ? "done"
                  : "pending",
            },
          ] satisfies StepValidationCheck[],
        };
      case 2:
        return {
          title: "Training schedule",
          description: "Make sure availability and sparring rules fit together before moving on.",
          checks: [
            {
              label: form.training_availability.length
                ? "Training availability has at least one selected day."
                : "Pick at least one training availability option.",
              status: form.training_availability.length ? "done" : "pending",
            },
            {
              label: availabilityConsistency.hardError
                ? availabilityConsistency.hardError
                : "Availability supports the planned sessions per week.",
              status: availabilityConsistency.hardError ? "warning" : "done",
            },
            {
              label: sparringConsistency.hardError
                ? sparringConsistency.hardError
                : "Hard sparring and support work sit on valid days.",
              status: sparringConsistency.hardError ? "warning" : "done",
            },
            ...(hardSparringWarning.message
              ? [{
                  label: hardSparringWarningAcknowledged
                    ? "Hard sparring recovery warning acknowledged."
                    : "Hard sparring recovery warning needs acknowledgement.",
                  status: hardSparringWarningAcknowledged ? "done" : "warning",
                } as const]
              : []),
          ] satisfies StepValidationCheck[],
        };
      case 3: {
        const guidedAreaMismatch = (form.guided_injuries ?? []).some((injury) => hasGuidedInjuryDescriptorWithoutArea(injury));
        return {
          title: "Restrictions and recovery",
          description: "Confirm injury detail is specific enough for safe loading decisions.",
          checks: [
            {
              label: noRestrictions || !guidedAreaMismatch
                ? "Restriction entries are specific enough to save."
                : "Add a pain area or body part before choosing severity or trend.",
              status: noRestrictions || !guidedAreaMismatch ? "done" : "pending",
            },
          ] satisfies StepValidationCheck[],
        };
      }
      case PERFORMANCE_STEP_INDEX:
        return {
          title: "Performance focus",
          description: "Keep goals and weak areas inside the camp-specific focus cap.",
          checks: [
            {
              label: form.fight_date
                ? `Fight date is set, so the focus cap for ${performanceFocusWindowLabel} is active.`
                : "Set the fight date to activate the focus cap guidance.",
              status: form.fight_date ? "done" : "pending",
            },
            {
              label: performanceFocusCapExceeded
                ? performanceFocusValidation.errorMessage ?? "Reduce your goals and weak areas to get back under the cap."
                : performanceFocusCapTitle,
              status: performanceFocusCapExceeded ? "warning" : "done",
            },
            {
              label: performanceFocusCapDetail,
              status: performanceFocusCapExceeded ? "warning" : "done",
            },
          ] satisfies StepValidationCheck[],
        };
      default:
        return {
          title: "Final pre-check",
          description: "Review the saved inputs, fix anything still open, then generate the plan.",
          checks: reviewChecklistItems,
        };
    }
  })();
  const unresolvedCurrentChecks = currentStepValidation.checks.filter((check) => check.status !== "done");
  const actionBarTitle = currentStep === steps.length - 1 ? "Generate plan" : `Step ${currentStep + 1}: ${steps[currentStep]}`;
  const actionBarSummary = unresolvedCurrentChecks.length
    ? currentStep === steps.length - 1
      ? `${unresolvedCurrentChecks.length} check${unresolvedCurrentChecks.length === 1 ? "" : "s"} still need attention before generation.`
      : `${unresolvedCurrentChecks.length} check${unresolvedCurrentChecks.length === 1 ? "" : "s"} left before you continue.`
    : currentStep === steps.length - 1
      ? "All required inputs are ready to generate."
      : "This step is ready to continue.";
  const formActionPending = isPending;

  return (
    <RequireAuth>
      <section className="panel onboarding-panel">
        <div className="section-heading onboarding-heading-desktop">
          <div className="athlete-motion-slot athlete-motion-header">
            <p className="kicker">{t("eyebrow")}</p>
            <h1>{t("title")}</h1>
            <p className="muted">{appText("text_ab3f8d47c2e2")}</p>
            <Link href="/quick-build" className="ghost-button onboarding-quick-build-link">
              {appText("text_0cfd4a365725")}</Link>
          </div>
        </div>

        <MobileOnboardingHeader
          currentStep={currentStep}
          isOpen={isMobileProgressOpen}
          onToggle={() => setIsMobileProgressOpen((current) => !current)}
          onStepSelect={handleStepSelect}
          saveStatus={saveStatus}
          lastSavedAt={lastSavedAt}
          onRetrySave={handleSaveDraft}
          retrySaveDisabled={formActionPending}
        />

        <div className="athlete-motion-slot athlete-motion-status onboarding-progress-desktop">
          <OnboardingProgressStrip currentStep={currentStep} />
          <AutoSaveIndicator
            status={saveStatus}
            lastSavedAt={lastSavedAt}
            onRetry={handleSaveDraft}
            retryDisabled={formActionPending}
          />
          <StepPills currentStep={currentStep} onStepSelect={handleStepSelect} />
        </div>

        {daysOutCtx.uiHints.fight_proximity_banner ? (
          <div className="fight-proximity-banner" role="status">
            {daysOutCtx.uiHints.fight_proximity_banner}
          </div>
        ) : null}

        <StepValidationPanel
          stepLabel={steps[currentStep]}
          title={currentStepValidation.title}
          description={currentStepValidation.description}
          checks={currentStepValidation.checks}
        />

        {currentStep === 0 ? (
          <div className="step-layout onboarding-step-layout onboarding-step-layout-profile">
            <div className="step-main athlete-motion-slot athlete-motion-main onboarding-step-main">
              {refiningFromQuickBuild ? (
                <p className="quick-build-refine-notice" role="status">
                  {appText("text_f9c1c4eba256")}</p>
              ) : null}
              <OnboardingTrustNote />
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">{appText("text_999f23fcd7be")}</p>
                  <h2 className="form-section-title">{t("coreDetails")}</h2>
                </div>
                <p className="muted">{appText("text_12049a5a705e")}</p>
                <div className="form-grid onboarding-profile-core-grid">
                  <div className="field">
                    <label htmlFor="fullName">{appText("text_f13a64ba2fea")}</label>
                    <input
                      id="fullName"
                      name="name"
                      autoComplete="name"
                      value={form.athlete.full_name}
                      onChange={(event) => updateAthlete("full_name", event.target.value)}
                      maxLength={ATHLETE_FULL_NAME_MAX}
                      required
                    />
                  </div>
                  <div className={`field${invalidFieldId === "technicalStyle" ? " field-invalid" : ""}`}>
                    <label htmlFor="technicalStyle">{appText("text_6cf00167f1fa")}</label>
                    <CustomSelect
                      id="technicalStyle"
                      value={form.athlete.technical_style?.[0] ?? ""}
                      options={TECHNICAL_STYLE_OPTIONS}
                      placeholder={appText("text_287fff31e50b")}
                      includeEmptyOption
                      invalid={invalidFieldId === "technicalStyle"}
                      describedBy={invalidFieldId === "technicalStyle" ? "technicalStyle-error" : undefined}
                      onChange={(value) => updateAthlete("technical_style", value ? [value] : [])}
                    />
                    {invalidFieldId === "technicalStyle" && error ? (
                      <p id="technicalStyle-error" className="error-text" role="alert">{error}</p>
                    ) : null}
                  </div>
                  <div className="field">
                    <label htmlFor="tacticalStyle">{appText("text_4da9e1d10c36")}</label>
                    <CustomSelect
                      id="tacticalStyle"
                      value={form.athlete.tactical_style[0] ?? ""}
                      options={TACTICAL_STYLE_OPTIONS}
                      placeholder={appText("text_9c1df520a354")}
                      includeEmptyOption
                      onChange={(value) => updateAthlete("tactical_style", value ? [value] : [])}
                    />
                    <p className="muted">{appText("text_eafc3a2f6585")}</p>
                  </div>
                </div>
              </article>

              <OptionalDetails
                title={appText("text_3b3581cb91a1")}
                hint={appText("text_1459230dc23a")}
              >
                <div className="form-grid onboarding-profile-detail-grid">
                  <div className="field">
                    <label htmlFor="sex">{appText("text_953dd6f2b461")}</label>
                    <CustomSelect
                      id="sex"
                      value={form.athlete.sex ?? ""}
                      options={SEX_OPTIONS}
                      placeholder={appText("text_8e99ebc415fe")}
                      includeEmptyOption
                      onChange={(value) => updateAthlete("sex", (value || null) as PlanRequest["athlete"]["sex"])}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="age">{appText("text_39b7370f30a3")}</label>
                    <input id="age" type="number" min="0" inputMode="numeric" value={form.athlete.age ?? ""} onChange={(event) => updateAthlete("age", numberOrNull(event.target.value))} />
                  </div>
                  <div className="field">
                    <label htmlFor="weightKg">{appText("text_b48ca1a31a0f")}</label>
                    <input id="weightKg" type="number" min="0" step="0.1" inputMode="decimal" disabled={!healthConsentGranted} value={healthConsentGranted ? (form.athlete.weight_kg ?? "") : ""} onChange={(event) => updateAthlete("weight_kg", numberOrNull(event.target.value))} />
                    <p className="muted">{healthConsentGranted ? appText("text_dec14b0e69ad") : HEALTH_CONSENT_BLOCKED_MESSAGE}</p>
                  </div>
                  <div className="field">
                    <label htmlFor="heightCm">{appText("text_19ce4b01c53f")}</label>
                    <input id="heightCm" type="number" min="0" step="1" inputMode="numeric" value={form.athlete.height_cm ?? ""} onChange={(event) => updateAthlete("height_cm", integerOrNull(event.target.value))} />
                  </div>
                  <div className="field">
                    <label htmlFor="stance">{appText("text_f30eedd9ae52")}</label>
                    <CustomSelect
                      id="stance"
                      value={form.athlete.stance ?? ""}
                      options={STANCE_OPTIONS}
                      placeholder={appText("text_3248d1989701")}
                      includeEmptyOption
                      onChange={(value) => updateAthlete("stance", value)}
                    />
                  </div>
                  {/* Not shown to under-18s. UNLXCK provides them no weight-cut
                      guidance, so a fight-week target has no feature to serve —
                      and the Children's Code says a child's data is minimised to
                      what the active feature needs. The backend strips the field
                      too, so hiding it here is presentation, not enforcement. */}
                  {isMinorAthlete ? null : (
                    <div className="field">
                      <label htmlFor="targetWeightKg">{appText("text_33814df80c78")}</label>
                      <input id="targetWeightKg" type="number" min="0" step="0.1" inputMode="decimal" disabled={!healthConsentGranted} value={healthConsentGranted ? (form.athlete.target_weight_kg ?? "") : ""} onChange={(event) => updateAthlete("target_weight_kg", numberOrNull(event.target.value))} />
                      <p className="muted">{healthConsentGranted ? appText("text_bc71100118df") : HEALTH_CONSENT_BLOCKED_MESSAGE}</p>
                    </div>
                  )}
                  <div className="field">
                    <label htmlFor="status">{appText("text_51f2263889c5")}</label>
                    <CustomSelect
                      id="status"
                      value={form.athlete.professional_status ?? ""}
                      options={PROFESSIONAL_STATUS_OPTIONS}
                      placeholder={appText("text_3330603e1f93")}
                      includeEmptyOption
                      onChange={(value) => updateAthlete("professional_status", value)}
                    />
                  </div>
                  <div className={`field field-span-full${invalidFieldId === "record" || recordHasError ? " field-invalid" : ""}`}>
                    <label htmlFor="record">{appText("text_bfdd510698ef")}</label>
                    <input
                      id="record"
                      value={form.athlete.record ?? ""}
                      onChange={(event) => updateAthlete("record", sanitizeRecordInput(event.target.value))}
                      placeholder={appText("text_77ade5f7a47e")}
                      inputMode="text"
                      maxLength={RECORD_MAX}
                      aria-invalid={invalidFieldId === "record" || recordHasError ? true : undefined}
                      aria-describedby={invalidFieldId === "record" ? "record-error" : undefined}
                    />
                    <p className="muted">{appText("text_9726eaf28407")}<code>{appText("text_8708c70236fb")}</code> {appText("text_7175517a370b")}<code>{appText("text_874ffb6fd0f5")}</code>{appText("text_cdb4ee2aea69")}</p>
                    {invalidFieldId === "record" && error ? (
                      <p id="record-error" className="error-text" role="alert">{error}</p>
                    ) : recordHasError ? (
                      <p className="error-text">{t("recordHint")}</p>
                    ) : null}
                  </div>
                </div>
              </OptionalDetails>
            </div>

            <aside className="step-aside athlete-motion-slot athlete-motion-rail onboarding-step-aside">
              <div className="support-panel">
                <div className="form-section-header">
                  <p className="kicker">{appText("text_3225f9ee870f")}</p>
                  <h2 className="form-section-title">{t("currentSelections")}</h2>
                </div>
                <ul className="summary-list">
                  <li>{appText("text_2683cad48a14")}{formatValue(form.athlete.full_name)}</li>
                  <li>{appText("text_10327edbbd9a")}{technicalStyleLabel}</li>
                  <li>{appText("text_32b113b526ae")}{tacticalStyleLabel}</li>
                  <li>{appText("text_17494fb91931")}{stanceLabel}</li>
                  <li>{appText("text_6aef8922779c")}{statusLabel}</li>
                  <li>{appText("text_3dffc2d69c8b")}{formatValue(form.athlete.record)}</li>
                </ul>
              </div>
            </aside>
          </div>
        ) : null}

        {currentStep === 1 ? (
          <div className="step-layout onboarding-step-layout onboarding-step-layout-restrictions">
            <div className="step-main athlete-motion-slot athlete-motion-main onboarding-step-main">
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">{appText("text_af7f44f5e27e")}</p>
                  <h2 className="form-section-title">{t("timingLoad")}</h2>
                </div>
                <div className="form-grid onboarding-fight-grid">
                  <div className={`field${invalidFieldId === "fightDate" ? " field-invalid" : ""}`}>
                    <label htmlFor="fightDate">{appText("text_86a6123f76f8")}</label>
                    <input
                      id="fightDate"
                      type="date"
                      min={getTodayIsoDate()}
                      value={form.fight_date}
                      disabled={noScheduledFight}
                      onChange={(event) => updateField("fight_date", event.target.value)}
                      aria-invalid={invalidFieldId === "fightDate" ? true : undefined}
                      aria-describedby={invalidFieldId === "fightDate" ? "fightDate-error" : undefined}
                    />
                    <label className={`inline-warning-ack inline-warning-ack-subtle ${noScheduledFight ? "inline-warning-ack-checked" : ""}`.trim()}>
                      <input
                        type="checkbox"
                        checked={noScheduledFight}
                        onChange={(event) => {
                          const checked = event.target.checked;
                          setNoScheduledFight(checked);
                          setForm((current) => applyNoScheduledFightSnapshot(current, checked));
                        }}
                      />
                      <span className="inline-warning-ack-copy">{appText("text_f9895e2e6121")}</span>
                    </label>
                    {invalidFieldId === "fightDate" && error ? (
                      <p id="fightDate-error" className="error-text" role="alert">{error}</p>
                    ) : null}
                  </div>
                  <div className={`field${invalidFieldId === "roundCount" ? " field-invalid" : ""}`}>
                    <label htmlFor="roundCount">{appText("text_08744ab667ea")}</label>
                    <CustomSelect
                      id="roundCount"
                      value={parsedRounds.roundCount}
                      options={ROUND_COUNT_OPTIONS}
                      placeholder={appText("text_c6d054a3317f")}
                      includeEmptyOption
                      invalid={invalidFieldId === "roundCount"}
                      describedBy={invalidFieldId === "roundCount" ? "roundCount-error" : undefined}
                      onChange={(value) => updateRoundsField("roundCount", value)}
                    />
                    {invalidFieldId === "roundCount" && error ? (
                      <p id="roundCount-error" className="error-text" role="alert">{error}</p>
                    ) : null}
                  </div>
                  <div className={`field${invalidFieldId === "roundDuration" ? " field-invalid" : ""}`}>
                    <label htmlFor="roundDuration">{appText("text_1cd4f252cb74")}</label>
                    <CustomSelect
                      id="roundDuration"
                      value={parsedRounds.roundDuration}
                      options={ROUND_DURATION_OPTIONS}
                      placeholder={appText("text_9a90dae7f2ce")}
                      includeEmptyOption
                      invalid={invalidFieldId === "roundDuration"}
                      describedBy={invalidFieldId === "roundDuration" ? "roundDuration-error" : undefined}
                      onChange={(value) => updateRoundsField("roundDuration", value)}
                    />
                    {invalidFieldId === "roundDuration" && error ? (
                      <p id="roundDuration-error" className="error-text" role="alert">{error}</p>
                    ) : null}
                  </div>
                  {shouldHideField(daysOutCtx, "weekly_training_frequency") ? (
                    <div className="field field-span-full">
                      <p className="muted" style={{ opacity: 0.5 }}>{appText("text_9dfc1652fef1")}</p>
                    </div>
                  ) : (
                    <div
                      className={`field field-span-full${invalidFieldId === "sessionsPerWeek" ? " field-invalid" : ""}`}
                      style={shouldDeEmphasizeField(daysOutCtx, "weekly_training_frequency") ? { opacity: 0.55 } : undefined}
                    >
                      <label htmlFor="sessionsPerWeek">{appText("text_769f29d88218")}</label>
                      <input
                        id="sessionsPerWeek"
                        type="number"
                        min="1"
                        max="6"
                        inputMode="numeric"
                        disabled={shouldDisableField(daysOutCtx, "weekly_training_frequency")}
                        value={form.weekly_training_frequency ?? ""}
                        onChange={(event) => {
                          const nextValue = numberOrNull(event.target.value);
                          updateField(
                            "weekly_training_frequency",
                            nextValue === null ? null : Math.min(Math.max(nextValue, 1), 6),
                          );
                        }}
                        aria-invalid={invalidFieldId === "sessionsPerWeek" ? true : undefined}
                        aria-describedby={invalidFieldId === "sessionsPerWeek" ? "sessionsPerWeek-error" : undefined}
                      />
                      <p className="muted">
                        {getFieldHelperText(daysOutCtx, "weekly_training_frequency") ||
                          appText("text_e6c0df2df287")}
                      </p>
                      {invalidFieldId === "sessionsPerWeek" && error ? (
                        <p id="sessionsPerWeek-error" className="error-text" role="alert">{error}</p>
                      ) : null}
                    </div>
                  )}
                </div>
              </article>

              <OptionalDetails
                title={appText("text_c83bec1f0284")}
                hint={appText("text_0ed73c07bfe1")}
              >
                {healthConsentGranted ? (
                <div className="field">
                  <label htmlFor="fatigueLevel">{appText("text_cf260a4f2c6e")}</label>
                  <LevelSlider
                    id="fatigueLevel"
                    ariaLabel={appText("text_cf260a4f2c6e")}
                    value={(form.fatigue_level ?? "low") as LevelValue}
                    onChange={(value) => updateField("fatigue_level", value)}
                  />
                  <p className="muted">{appText("text_974a55c1dbdf")}</p>
                </div>
                ) : <p className="muted">{HEALTH_CONSENT_BLOCKED_MESSAGE}</p>}
              </OptionalDetails>
            </div>

            <aside className="step-aside athlete-motion-slot athlete-motion-rail onboarding-step-aside">
              <div className="support-panel">
                <div className="form-section-header">
                  <p className="kicker">{appText("text_609ed91cf1f3")}</p>
                  <h2 className="form-section-title">{t("currentSetup")}</h2>
                </div>
                <ul className="summary-list">
                  <li>{appText("text_f65bea824e6f")}{formatFightDateValue(form.fight_date)}</li>
                  <li>{appText("text_6b8a8e381c7d")}{formatValue(form.rounds_format)}</li>
                  <li>{appText("text_42689438d447")}{formatValue(form.weekly_training_frequency)}</li>
                  <li>{appText("text_a703783e38c0")}{formatValue(form.fatigue_level || "low")}</li>
                </ul>
              </div>
              <div className="support-panel">
                <p className="kicker">{appText("text_10af9928ba80")}</p>
                <p className="muted">{appText("text_c5f2f3e4becc")}</p>
              </div>
            </aside>
          </div>
        ) : null}

        {currentStep === 2 ? (
          <div className="step-layout onboarding-step-layout">
            <div className="step-main athlete-motion-slot athlete-motion-main onboarding-step-main">
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">{appText("text_f4830a1dae29")}</p>
                  <h2 className="form-section-title">{t("trainingAvailability")}</h2>
                </div>
                {shouldHideField(daysOutCtx, "training_availability") ? (
                  <div className="field">
                    <p className="muted" style={{ opacity: 0.5 }}>{appText("text_c910c94861d8")}</p>
                  </div>
                ) : (
                <>
                  <CheckboxGroup
                    id="trainingAvailabilityGroup"
                    label={appText("text_d0c4e32176bb")}
                    options={TRAINING_AVAILABILITY_OPTIONS}
                    selectedValues={form.training_availability}
                    onToggle={(value) => toggleFieldValue("training_availability", value)}
                    disableAll={shouldDisableField(daysOutCtx, "training_availability")}
                    invalid={invalidFieldId === "trainingAvailabilityGroup"}
                    describedBy={invalidFieldId === "trainingAvailabilityGroup" ? "trainingAvailabilityGroup-error" : undefined}
                  />
                  {invalidFieldId === "trainingAvailabilityGroup" && error ? (
                    <p id="trainingAvailabilityGroup-error" className="error-text" role="alert">{error}</p>
                  ) : null}
                </>
                )}
                {availabilityConsistency.hardError || availabilityConsistency.softWarning ? (
                  <div
                    id="availabilityConsistencyAlert"
                    className={`support-panel ${availabilityConsistency.hardError ? "support-panel-alert" : ""}${invalidFieldId === "availabilityConsistencyAlert" ? " field-invalid" : ""}`.trim()}
                    tabIndex={invalidFieldId === "availabilityConsistencyAlert" ? -1 : undefined}
                    aria-invalid={invalidFieldId === "availabilityConsistencyAlert" ? true : undefined}
                  >
                    <p className="kicker">{appText("text_76766aa318c3")}</p>
                    <p className={availabilityConsistency.hardError ? "error-text" : "muted"}>
                      {availabilityConsistency.hardError ?? availabilityConsistency.softWarning}
                    </p>
                  </div>
                ) : null}
              </article>
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">{appText("text_cf1da5594e96")}</p>
                  <h2 className="form-section-title">{t("combatLoad")}</h2>
                </div>
                <p className="muted">
                  {appText("text_ad7e27f6d751")}</p>
                {shouldHideField(daysOutCtx, "hard_sparring_days") ? (
                  <div className="field">
                    <p className="muted" style={{ opacity: 0.5 }}>{appText("text_dc29cb08269e")}</p>
                  </div>
                ) : (
                <>
                <CheckboxGroup
                  label={appText("text_7ef2a3f6f1a2")}
                  options={TRAINING_AVAILABILITY_OPTIONS}
                  selectedValues={form.hard_sparring_days}
                  onToggle={(value) => toggleFieldValue("hard_sparring_days", value)}
                  disableAll={shouldDisableField(daysOutCtx, "hard_sparring_days")}
                  getOptionDisabledReason={(option, checked) =>
                    checked
                      ? null
                      : lockedFightWeekday === option.value
                        ? fightDayLockReason
                        : !form.training_availability.includes(option.value)
                          ? "Add to availability first"
                          : form.support_work_days.includes(option.value)
                            ? "Already tagged as Light Combat"
                            : form.hard_sparring_days.length >= HARD_SPARRING_DAY_CAP
                              ? `Hard sparring cap (${HARD_SPARRING_DAY_CAP}) reached`
                              : null
                  }
                />
                <div className="field">
                  <p className="muted">
                    {getFieldHelperText(daysOutCtx, "hard_sparring_days") ||
                      appText("text_008fc1dbb200")}
                  </p>
                </div>
                {hardSparringWarning.message ? (
                  <div
                    id="hardSparringAck"
                    className={`inline-warning-banner ${hardSparringWarningLocked ? "inline-warning-banner-alert" : ""}${invalidFieldId === "hardSparringAck" ? " field-invalid" : ""}`.trim()}
                    tabIndex={invalidFieldId === "hardSparringAck" ? -1 : undefined}
                    aria-invalid={invalidFieldId === "hardSparringAck" ? true : undefined}
                    aria-describedby={invalidFieldId === "hardSparringAck" ? "hardSparringAck-error" : undefined}
                  >
                    <p className="inline-warning-banner-label">{appText("text_fad222d2101e")}</p>
                    <p className={hardSparringWarningLocked ? "error-text" : "muted"}>{hardSparringWarning.message}</p>
                    <label className={`inline-warning-ack ${hardSparringWarningAcknowledged ? "inline-warning-ack-checked" : ""}`.trim()}>
                      <input
                        type="checkbox"
                        checked={hardSparringWarningAcknowledged}
                        onChange={(event) => {
                          setAcknowledgedHardSparringWarningKey(
                            event.target.checked ? hardSparringWarning.acknowledgementContextKey : null,
                          );
                        }}
                      />
                      <span className="inline-warning-ack-copy">{appText("text_482e260b94ec")}</span>
                    </label>
                    {invalidFieldId === "hardSparringAck" && error ? (
                      <p id="hardSparringAck-error" className="error-text" role="alert">{error}</p>
                    ) : null}
                  </div>
                ) : null}
                </>
                )}
                {shouldHideField(daysOutCtx, "support_work_days") ? (
                  <div className="field">
                    <p className="muted" style={{ opacity: 0.5 }}>{appText("text_5c4891fb37c1")}</p>
                  </div>
                ) : (
                <>
                <CheckboxGroup
                  label={appText("text_7ea5be859a70")}
                  options={TRAINING_AVAILABILITY_OPTIONS}
                  selectedValues={form.support_work_days}
                  onToggle={(value) => toggleFieldValue("support_work_days", value)}
                  disableAll={shouldDisableField(daysOutCtx, "support_work_days")}
                  getOptionDisabledReason={(option, checked) =>
                    checked
                      ? null
                      : lockedFightWeekday === option.value
                        ? fightDayLockReason
                        : !form.training_availability.includes(option.value)
                          ? "Add to availability first"
                          : form.hard_sparring_days.includes(option.value)
                            ? "Already tagged as hard sparring"
                            : null
                  }
                />
                <div className="field">
                  <p className="muted">
                    {getFieldHelperText(daysOutCtx, "support_work_days") ||
                      appText("text_13ce29ff5c2d")
                    }
                  </p>
                </div>
                </>
                )}
                {sparringConsistency.hardError || sparringConsistency.softWarning ? (
                  <div
                    id="sparringConsistencyAlert"
                    className={`support-panel ${sparringConsistency.hardError ? "support-panel-alert" : ""}${invalidFieldId === "sparringConsistencyAlert" ? " field-invalid" : ""}`.trim()}
                    tabIndex={invalidFieldId === "sparringConsistencyAlert" ? -1 : undefined}
                    aria-invalid={invalidFieldId === "sparringConsistencyAlert" ? true : undefined}
                  >
                    <p className="kicker">{appText("text_76e350e56367")}</p>
                    <p className={sparringConsistency.hardError ? "error-text" : "muted"}>
                      {sparringConsistency.hardError ?? sparringConsistency.softWarning}
                    </p>
                  </div>
                ) : null}
                {!noScheduledFight && !form.hard_sparring_days.length && !form.support_work_days.length ? (
                  <div className="field">
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => {
                        setNoScheduledFight(true);
                        setForm((current) => applyNoScheduledFightSnapshot(current, true));
                        setError(null);
                        setInvalidFieldId(null);
                        setValidationFocusRequest(null);
                        setMessage(appText("text_43f15dfa7ec4"));
                      }}
                    >
                      {appText("text_d5ca03dcf519")}</button>
                  </div>
                ) : null}
              </article>
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">{appText("text_e89b30aa1dc3")}</p>
                  <h2 className="form-section-title">{t("equipment")}</h2>
                </div>
                <EquipmentSelector
                  selectedValues={form.equipment_access}
                  onToggle={(value) => toggleFieldValue("equipment_access", value)}
                />
              </article>
              {shouldHideField(daysOutCtx, "training_preference") ? null : (
              <OptionalDetails
                title={appText("text_f34d9859411f")}
                hint={appText("text_e24925d1902d")}
              >
                <div className="field" style={shouldDeEmphasizeField(daysOutCtx, "training_preference") ? { opacity: 0.55 } : undefined}>
                  <label htmlFor="trainingPreference">{appText("text_615d96e7082f")}</label>
                  <textarea
                    id="trainingPreference"
                    disabled={shouldDisableField(daysOutCtx, "training_preference")}
                    value={form.training_preference ?? ""}
                    onChange={(event) => updateField("training_preference", event.target.value)}
                    maxLength={TRAINING_PREFERENCE_MAX}
                    placeholder={appText("text_0bf41a9dc509")}
                  />
                  <p className="muted">
                    {getFieldHelperText(daysOutCtx, "training_preference") ||
                      appText("text_bae5a6ce490e")}
                  </p>
                </div>
              </OptionalDetails>
              )}
            </div>

            <aside className="step-aside athlete-motion-slot athlete-motion-rail onboarding-step-aside">
              <div className="support-panel">
                <div className="form-section-header">
                  <p className="kicker">{appText("text_48571f7d9b50")}</p>
                  <h2 className="form-section-title">{t("selectedAvailability")}</h2>
                </div>
                <ul className="summary-list">
                  <li>{appText("text_9fbccee24cd0")}{selectedTrainingAvailability}</li>
                  <li>{appText("text_3e4ee11ba575")}{selectedHardSparring}</li>
                  <li>{appText("text_691c518bfeb7")}{selectedSupportWorkDays}</li>
                  <li>{appText("text_a8e521b6f956")}{selectedEquipmentAccess}</li>
                </ul>
              </div>
              <div className="support-panel">
                <p className="kicker">{appText("text_a0dc191bc1d4")}</p>
                <p className="muted">{appText("text_a7e9aa5c9638")}</p>
              </div>
            </aside>
          </div>
        ) : null}

        {currentStep === 3 ? (
          <div className="step-layout onboarding-step-layout onboarding-step-layout-restrictions">
            <div className="step-main athlete-motion-slot athlete-motion-main onboarding-step-main">
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">{appText("text_25ed77282d99")}</p>
                  <h2 className="form-section-title">{t("injuries")}</h2>
                </div>
                {healthConsentGranted ? <SafetyNote showRedFlags>{INJURY_INTAKE_SAFETY}</SafetyNote> : null}
                {!healthConsentGranted ? (
                  <div className="support-panel gi-empty-state compact-gap" aria-disabled="true">
                    <p className="muted">{HEALTH_CONSENT_BLOCKED_MESSAGE}</p>
                  </div>
                ) : noRestrictions ? (
                  // Empty state — a single inline CTA reveals the body map and a
                  // first card, instead of asking the athlete to untick a box first.
                  <div className="support-panel gi-empty-state compact-gap">
                    <p className="kicker">{appText("text_dc9beee1bf46")}</p>
                    <p className="muted">{appText("text_75656ba82aed")}</p>
                    <button type="button" className="injury-card-add-btn" onClick={() => handleNoRestrictionsChange(false)}>
                      <span aria-hidden="true">{appText("text_a318c24216de")}</span> {appText("text_ec7993bccfaf")}</button>
                  </div>
                ) : (
                  <>
                    {showClearInjuriesConfirm ? (
                      <div className="gi-clear-confirm-panel" role="alertdialog" aria-live="polite">
                        <p className="gi-clear-confirm-title">{appText("text_44cedb418919")}</p>
                        <p className="muted">{appText("text_20aad01adbae")}</p>
                        <div className="gi-clear-confirm-actions">
                          <button type="button" className="secondary-button" onClick={() => setShowClearInjuriesConfirm(false)}>{t("keepInjuries")}</button>
                          <button type="button" className="danger-button" onClick={handleConfirmClearInjuries}>{t("clearInjuries")}</button>
                        </div>
                      </div>
                    ) : null}
                    {pendingInjuryRemovalIndex !== null ? (
                      <div ref={pendingRemovalRef} className="gi-clear-confirm-panel gi-remove-confirm-panel" role="alertdialog" aria-live="polite">
                        <p className="gi-clear-confirm-title">{appText("text_75cd7c00eba0")}</p>
                        <p className="muted">{appText("text_0550a8174cc3")}</p>
                        <div className="gi-clear-confirm-actions">
                          <button type="button" className="secondary-button" onClick={handleCancelRemovePendingInjury}>{t("keepInjury")}</button>
                          <button type="button" className="danger-button" onClick={handleConfirmRemovePendingInjury}>{t("removeInjury")}</button>
                        </div>
                      </div>
                    ) : null}
                    <div className="injury-body-map-layout">
                      <div className="injury-body-map-col">
                        <BodyMap
                          side={bodyMapSide}
                          selections={guidedInjuries
                            .filter((injury) => injury.area.trim() || injury.zone)
                            .map((injury) => ({
                              zone: injury.zone || undefined,
                              label: injury.area,
                              severity: normalizeGuidedInjurySeverity(injury.severity) || undefined,
                            }))}
                          onZoneSelect={handleBodyMapZoneSelect}
                          onSideChange={setBodyMapSide}
                        />
                      </div>
                      <div className="injury-cards-col">
                        <div className="injury-card-stack">
                          {guidedInjuries.map((injury, index) => {
                            const cardId = `guidedInjuryCard-${index}`;
                            const isInvalidCard = invalidFieldId === cardId;
                            return (
                              <div
                                key={`guided-injury-${index}`}
                                id={cardId}
                                className={isInvalidCard ? "field-invalid" : undefined}
                                tabIndex={isInvalidCard ? -1 : undefined}
                                aria-invalid={isInvalidCard ? true : undefined}
                                aria-describedby={isInvalidCard ? `${cardId}-error` : undefined}
                              >
                                <GuidedInjuryCard
                                  injury={injury}
                                  index={index}
                                  isActive={activeGuidedInjuryIndex === index}
                                  onToggleActive={() => {
                                    if (activeGuidedInjuryIndex === index) {
                                      setActiveGuidedInjuryIndex(null);
                                    } else {
                                      handleEditGuidedInjury(index);
                                    }
                                  }}
                                  onUpdate={(key, value) => updateGuidedInjury(index, key, value)}
                                  onRemove={() => handleRequestRemoveGuidedInjury(index)}
                                />
                                {isInvalidCard && error ? (
                                  <p id={`${cardId}-error`} className="error-text" role="alert">{error}</p>
                                ) : null}
                              </div>
                            );
                          })}
                        </div>

                        <div className="injury-card-add-row">
                          <button type="button" className="injury-card-add-btn" onClick={handleAddGuidedInjury}>
                            <span aria-hidden="true">{appText("text_a318c24216de")}</span> {appText("text_85290ffc8690")}</button>
                        </div>
                      </div>
                    </div>
                    <button type="button" className="gi-notes-toggle gi-no-restrictions-btn" onClick={() => handleNoRestrictionsChange(true)}>
                      {appText("text_fa5225944b3e")}</button>
                  </>
                )}
              </article>
            </div>
          </div>
        ) : null}

        {currentStep === 4 ? (
          <div className="step-layout onboarding-step-layout">
            <div className="step-main athlete-motion-slot athlete-motion-main onboarding-step-main">
              <article
                className={`focus-cap-card ${performanceFocusCapExceeded ? "focus-cap-card-alert" : performanceFocusCapReached ? "focus-cap-card-full" : ""}`.trim()}
                aria-label={performanceFocusCapTitle}
              >
                <span className="focus-cap-badge" aria-hidden="true">
                  {performanceFocusCapBadge}
                </span>
                <div className="focus-cap-copy">
                  <p className="focus-cap-label">{appText("text_01465d8d27b4")}</p>
                  <p className="focus-cap-hint">{performanceFocusCapHint}</p>
                </div>
              </article>
              {shouldHideField(daysOutCtx, "key_goals") ? (
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">{appText("text_467d76ab412f")}</p>
                  <h2 className="form-section-title">{t("goals")}</h2>
                </div>
                <p className="muted" style={{ opacity: 0.5 }}>{appText("text_8c1bc22a8a2a")}</p>
              </article>
              ) : (
              <article className="step-card" style={shouldDeEmphasizeField(daysOutCtx, "key_goals") ? { opacity: 0.55 } : undefined}>
                <div className="form-section-header">
                  <p className="kicker">{appText("text_467d76ab412f")}</p>
                  <h2 className="form-section-title">{t("goals")}</h2>
                </div>
                <CheckboxGroup
                  id="keyGoalsGroup"
                  label={appText("text_b33c23d73364")}
                  options={KEY_GOAL_OPTIONS}
                  selectedValues={form.key_goals}
                  onToggle={(value) => toggleFieldValue("key_goals", value)}
                  disableAdditionalSelections={performanceFocusCapReached}
                  capDisabledReason={keyGoalCapDisabledReason}
                  disableAll={shouldDisableField(daysOutCtx, "key_goals")}
                  getOptionDisabledReason={getKeyGoalDisabledReason}
                  invalid={invalidFieldId === "keyGoalsGroup"}
                  describedBy={invalidFieldId === "keyGoalsGroup" ? "keyGoalsGroup-error" : undefined}
                />
                {invalidFieldId === "keyGoalsGroup" && error ? (
                  <p id="keyGoalsGroup-error" className="error-text" role="alert">{error}</p>
                ) : null}
                {getFieldHelperText(daysOutCtx, "key_goals") ? (
                  <p className="muted">{getFieldHelperText(daysOutCtx, "key_goals")}</p>
                ) : null}
                {form.key_goals.length > 1 ? (
                  <div className="field">
                    <label htmlFor="primaryGoal">{appText("text_9638482b77fe")}</label>
                    <CustomSelect
                      id="primaryGoal"
                      value={form.primary_goal ?? ""}
                      options={KEY_GOAL_OPTIONS.filter((option) => form.key_goals.includes(option.value))}
                      placeholder={appText("text_408632ac6aa6")}
                      includeEmptyOption
                      onChange={(value) => updateField("primary_goal", value)}
                    />
                    <p className="muted">{appText("text_4ef27130ec1e")}</p>
                  </div>
                ) : null}
              </article>
              )}
              {shouldHideField(daysOutCtx, "weak_areas") ? (
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">{appText("text_6899141ffa88")}</p>
                  <h2 className="form-section-title">{t("weakAreas")}</h2>
                </div>
                <p className="muted" style={{ opacity: 0.5 }}>{appText("text_66b0fa5f7382")}</p>
              </article>
              ) : (
              <article className="step-card" style={shouldDeEmphasizeField(daysOutCtx, "weak_areas") ? { opacity: 0.55 } : undefined}>
                <div className="form-section-header">
                  <p className="kicker">{appText("text_6899141ffa88")}</p>
                  <h2 className="form-section-title">{t("weakAreas")}</h2>
                </div>
                <CheckboxGroup
                  label={appText("text_01335284ff74")}
                  options={WEAK_AREA_OPTIONS}
                  selectedValues={form.weak_areas}
                  onToggle={(value) => toggleFieldValue("weak_areas", value)}
                  disableAdditionalSelections={performanceFocusCapReached}
                  capDisabledReason={weakAreaCapDisabledReason}
                  disableAll={shouldDisableField(daysOutCtx, "weak_areas")}
                  getOptionDisabledReason={getWeakAreaDisabledReason}
                />
                {getFieldHelperText(daysOutCtx, "weak_areas") ? (
                  <p className="muted">{getFieldHelperText(daysOutCtx, "weak_areas")}</p>
                ) : null}
                {form.weak_areas.length > 1 ? (
                  <div className="field">
                    <label htmlFor="primaryWeakArea">{appText("text_f64d9415a04d")}</label>
                    <CustomSelect
                      id="primaryWeakArea"
                      value={form.primary_weak_area ?? ""}
                      options={WEAK_AREA_OPTIONS.filter((option) => form.weak_areas.includes(option.value))}
                      placeholder={appText("text_89d3e545ad1d")}
                      includeEmptyOption
                      onChange={(value) => updateField("primary_weak_area", value)}
                    />
                    <p className="muted">{appText("text_79ca90b1ed17")}</p>
                  </div>
                ) : null}
                <p className="muted">{appText("text_9f0597f46b6c")}</p>
              </article>
              )}
              {goalWeakAreaOverlaps.length ? (
                <article className="step-card priority-clarification-card">
                  <div className="form-section-header">
                    <p className="kicker">{appText("text_69efa4a77f7b")}</p>
                    <h2 className="form-section-title">{t("priorityDetail")}</h2>
                  </div>
                  <div className="priority-clarification-copy">
                    <p>{overlapClarificationPrompt}</p>
                    <p className="muted">{appText("text_6e6369ce8f24")}</p>
                  </div>
                  <div className="priority-clarification-options" role="radiogroup" aria-label={appText("text_b033141c40ba")}>
                    {goalWeakAreaOverlaps.map((overlap, overlapIndex) => {
                      const overlapClarificationOptions = getClarificationOptions(overlap.normalizedTag, form.athlete.technical_style, form.athlete.tactical_style);
                      const selectedDetail = form.goal_weakness_collision_details?.[overlapIndex]?.detail ?? "";
                      return (
                        <div key={overlap.tag} className="field">
                          <p><strong>{overlap.label}</strong></p>
                          {overlapClarificationOptions.map((option) => {
                            const checked = selectedDetail === option;
                            return (
                              <label
                                key={`${overlap.tag}-${option}`}
                                className={`priority-clarification-option${checked ? " priority-clarification-option-selected" : ""}`}
                              >
                                <input
                                  type="radio"
                                  name={`goalWeaknessCollisionDetail-${overlap.tag}`}
                                  value={option}
                                  checked={checked}
                                  onChange={() => {
                                    const next = [...(form.goal_weakness_collision_details ?? [])];
                                    const existing = next[overlapIndex] ?? { tag: overlap.tag, label: overlap.label, detail: "" };
                                    next[overlapIndex] = { ...existing, tag: overlap.tag, label: overlap.label, detail: option };
                                    updateField("goal_weakness_collision_details", next);
                                    if (overlapIndex === 0) updateField("goal_weakness_collision_detail", option);
                                  }}
                                />
                                <span>{option}</span>
                              </label>
                            );
                          })}
                        </div>
                      );
                    })}
                  </div>
                </article>
              ) : null}
              <OptionalDetails
                title={appText("text_7c82a1ceefad")}
                hint={appText("text_f053dcfd615b")}
              >
                <div className="form-grid">
                  <div className="field">
                    <label htmlFor="mindsetChallenges">{appText("text_f13717f1d45b")}</label>
                    <textarea
                      id="mindsetChallenges"
                      value={form.mindset_challenges ?? ""}
                      onChange={(event) => updateField("mindset_challenges", event.target.value)}
                      maxLength={MENTAL_BLOCKERS_MAX}
                      placeholder={appText("text_81a51c7e6903")}
                    />
                    <p className="muted">{appText("text_b84745310237")}</p>
                  </div>
                  <div className="field">
                    <label htmlFor="notes">{appText("text_d1bb371ff482")}</label>
                    <textarea
                      id="notes"
                      value={form.notes ?? ""}
                      onChange={(event) => updateField("notes", event.target.value)}
                      maxLength={PREVIOUS_PLAN_FEEDBACK_MAX}
                      placeholder={appText("text_35c46c4166d0")}
                    />
                    <p className="muted">{appText("text_9afc7c6c957e")}</p>
                  </div>
                </div>
              </OptionalDetails>
            </div>

            <aside className="step-aside athlete-motion-slot athlete-motion-rail onboarding-step-aside">
              <div className="support-panel">
                <div className="form-section-header">
                  <p className="kicker">{appText("text_646e52893fd0")}</p>
                  <h2 className="form-section-title">{t("selectedFocus")}</h2>
                </div>
                <ul className="summary-list">
                  <li>{appText("text_919512d71f37")}{selectedGoals}</li>
                  <li>{appText("text_74de0d1db889")}{selectedWeakAreas}</li>
                  <li>{appText("text_4f355a949579")}{formatValue(form.mindset_challenges)}</li>
                </ul>
              </div>
            </aside>
          </div>
        ) : null}

        {currentStep === 5 ? (
          <div className="step-layout onboarding-step-layout">
            <div className="step-main athlete-motion-slot athlete-motion-main onboarding-step-main">
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">{appText("text_aff0766a5290")}</p>
                  <h2 className="form-section-title">{t("capturedInput")}</h2>
                </div>
                <div className="review-columns">
                  <div className="review-column">
                    <article className="review-card">
                      <div className="review-card-header">
                        <p className="kicker">{appText("text_d696a35bdd18")}</p>
                        <h3 className="review-card-title">{t("athleteProfile")}</h3>
                      </div>
                      <ReviewDetailList items={profileReviewItems} />
                    </article>
                    <article className="review-card">
                      <div className="review-card-header">
                        <p className="kicker">{appText("text_36a798e3f392")}</p>
                        <h3 className="review-card-title">{t("availabilityEquipment")}</h3>
                      </div>
                      <ReviewDetailList items={trainingReviewItems} />
                    </article>
                  </div>
                  <div className="review-column">
                    <article className="review-card">
                      <div className="review-card-header">
                        <p className="kicker">{appText("text_af7f44f5e27e")}</p>
                        <h3 className="review-card-title">{t("campSetup")}</h3>
                      </div>
                      <ReviewDetailList items={campSetupReviewItems} />
                    </article>
                    <article className="review-card">
                      <div className="review-card-header">
                        <p className="kicker">{appText("text_442aded87a55")}</p>
                        <h3 className="review-card-title">{t("goalsWeakAreas")}</h3>
                      </div>
                      <ReviewDetailList items={performanceReviewItems} />
                    </article>
                    <article className="review-card">
                      <div className="review-card-header">
                        <p className="kicker">{appText("text_2b59190cc5bd")}</p>
                        <h3 className="review-card-title">{t("constraintsRisks")}</h3>
                      </div>
                      <ReviewDetailList items={constraintsReviewItems} />
                    </article>
                  </div>
                </div>
              </article>
            </div>

            <aside className="step-aside athlete-motion-slot athlete-motion-rail onboarding-step-aside">
              <div className="support-panel">
                <p className="kicker">{appText("text_25ed77282d99")}</p>
                <p className="muted">{appText("text_5bbf3a142c4d")}{restrictionSummary}</p>
              </div>
              <div className="support-panel">
                <p className="kicker">{appText("text_975be27ceb04")}</p>
                <p className="muted">{appText("text_ac6f7c517928")}</p>
                <div className="plan-summary-actions">
                  <Link href="/nutrition" className="ghost-button">
                    {appText("text_24e7448d62b8")}</Link>
                </div>
              </div>
            </aside>
          </div>
        ) : null}

        {message ? <div className="success-banner athlete-motion-slot athlete-motion-status">{translateUiText(appText, message)}</div> : null}
        {error ? (
          <div
            id="onboarding-error-banner"
            className="error-banner athlete-motion-slot athlete-motion-status"
            role="alert"
            aria-live="assertive"
          >
            {translateUiText(appText, error)}
          </div>
        ) : null}

        <div className="form-actions onboarding-action-bar athlete-motion-slot athlete-motion-rail">
          <div className="onboarding-action-bar-copy">
            <p className="kicker">{actionBarTitle}</p>
            <p className="muted">{actionBarSummary}</p>
          </div>
          <div className="onboarding-action-buttons">
            <button type="button" className="ghost-button onboarding-action-secondary" onClick={handleSaveDraft} disabled={formActionPending}>
              {isPending ? t("saving") : t("saveDraft")}
            </button>
            {currentStep > 0 ? (
              <button type="button" className="ghost-button onboarding-action-secondary" onClick={handleBack}>
                {t("back")}
              </button>
            ) : null}
            {currentStep < steps.length - 1 ? (
              <button type="button" className="cta onboarding-action-primary" onClick={handleNext} disabled={formActionPending}>
                {t("next")}
              </button>
            ) : (
              <>
                <button type="button" className="cta onboarding-action-primary" onClick={handleGenerate} disabled={formActionPending}>
                  {t("generate")}
                </button>
              </>
            )}
          </div>
        </div>
      </section>
    </RequireAuth>
  );
}
