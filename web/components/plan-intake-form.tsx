"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { BodyMap, type BodyMapSide } from "@/components/body-map";
import { CustomSelect } from "@/components/custom-select";
import { saveOnboardingDraft } from "@/lib/api";
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
  hasGuidedInjuryReviewRisk,
  hydrateGuidedInjuryStates,
  type GuidedInjuryState,
} from "@/lib/guided-injury";
import { GuidedInjuryCard } from "@/components/guided-injury-card";
import { LevelSlider, type LevelValue } from "@/components/rating-controls";
import { applyNoScheduledFightSnapshot, emptyPlanRequest, hydratePlanRequest, mergePlanRequestDraft } from "@/lib/onboarding";
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
  filterAvailablePerformanceFocusValues,
  getPerformanceFocusOptionAvailability,
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
          Retry
        </button>
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
  const progress = getOnboardingProgressState(currentStep);
  const content = (
    <>
      <div className="onboarding-progress-strip-topline">
        <p className="kicker">Intake progress</p>
        <span
          className={`onboarding-progress-badge ${progress.badgeText === "Ready" ? "onboarding-progress-badge-ready" : ""}`.trim()}
        >
          {progress.badgeText}
        </span>
      </div>
      <p className="onboarding-progress-strip-title">
        Step {progress.stepNumber} of {progress.totalSteps}
      </p>
      <div className="overview-progress-track onboarding-progress-track" role="presentation" aria-hidden="true">
        <span className="overview-progress-fill onboarding-progress-fill" style={{ width: `${progress.progressValue}%` }} />
      </div>
      <div className="onboarding-progress-strip-footer">
        <p className="overview-progress-helper onboarding-progress-helper">{progress.helperText}</p>
        {isExpandable ? (
          <span className="onboarding-progress-affordance" aria-hidden="true">
            <span className="onboarding-progress-affordance-label">{isExpanded ? "Close" : "All steps"}</span>
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
      <div ref={railRef} className="mobile-step-rail-scroll" aria-label="Intake steps">
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
  return (
    <div className="onboarding-heading-mobile">
      <div className="onboarding-mobile-header-copy">
        <p className="kicker">Advanced Intake</p>
        <p className="onboarding-mobile-title">Build your camp profile.</p>
        <p className="muted">Saved, resumable athlete intake.</p>
        <Link href="/quick-build" className="ghost-button onboarding-quick-build-link">
          Use Quick Build instead
        </Link>
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
}) {
  return (
    <div
      id={id}
      className={`field${invalid ? " field-invalid" : ""}`}
      role="group"
      aria-label={label}
      aria-invalid={invalid ? true : undefined}
      aria-describedby={describedBy}
      tabIndex={invalid ? -1 : undefined}
    >
      <span className="checkbox-group-label">{label}</span>
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
              <input type="checkbox" checked={checked} disabled={disabled} onChange={() => onToggle(option.value)} />
              <span className="checkbox-card-copy">
                <span className="checkbox-card-title">{option.label}</span>
                {daysOutDisabledReason ? <span className="checkbox-card-tag">{daysOutDisabledReason}</span> : null}
                {!daysOutDisabledReason && capDisabled ? (
                  <span className="checkbox-card-tag">{capDisabledReason || "Focus cap reached."}</span>
                ) : null}
              </span>
            </label>
          );
        })}
      </div>
    </div>
  );
}

function OptionalDetails({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <details className="overview-disclosure onboarding-optional-disclosure">
      <summary className="overview-disclosure-summary">
        <div className="overview-disclosure-copy">
          <p className="kicker">Optional</p>
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
  const unresolvedChecks = checks.filter((check) => check.status !== "done");

  return (
    <div
      className={`support-panel onboarding-validation-panel ${unresolvedChecks.length ? "onboarding-validation-panel-attention" : "onboarding-validation-panel-ready"}`.trim()}
      role="status"
      aria-live="polite"
    >
      <div className="onboarding-validation-header">
        <div className="onboarding-validation-copy">
          <p className="kicker">{stepLabel} check</p>
          <h2 className="form-section-title">{title}</h2>
          <p className="muted">{description}</p>
        </div>
        <span
          className={`onboarding-validation-badge ${unresolvedChecks.length ? "" : "onboarding-validation-badge-ready"}`.trim()}
        >
          {unresolvedChecks.length ? `${unresolvedChecks.length} left` : "Ready"}
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
  if (!nextForm.athlete.technical_style.length) return { message: "Select a technical style before continuing to review.", step: 0, fieldId: "technicalStyle" };
  if (!nextForm.fight_date && !options.noScheduledFight) return { message: "Choose your fight date or mark \"No scheduled fight\" before continuing to review.", step: 1, fieldId: "fightDate" };
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

type TrainingGateAction = "save_draft" | "next" | "step_select" | "generate";

type TrainingGateDecision =
  | { kind: "allow" }
  | { kind: "hard_error"; message: string; source: "availability" | "sparring" }
  | { kind: "warning_ack_required"; message: string; shouldRedirectToTraining: boolean };

export function PlanIntakeForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const refiningFromQuickBuild = searchParams.get("from") === "quick_build";
  const { me, session, replaceMe } = useAppSession();
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
  const recordHasError = !isValidRecordFormat(form.athlete.record ?? "");
  // Count injuries carrying a serious type or medical-safety flag so the
  // restrictions step can surface a single banner above the cards.
  const reviewRiskInjuryCount = guidedInjuries.filter((injury) => hasGuidedInjuryReviewRisk(injury)).length;

  // ── Days-out policy: compute field visibility/disablement ───────────
  const daysUntilFight = computeDaysUntilFight(form.fight_date);
  const daysOutCtx: DaysOutContext = buildDaysOutContext(daysUntilFight);

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
          return !getSparringConsistency(form.training_availability, form.hard_sparring_days, form.support_work_days).hardError;
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

    const currentDaysOutCtx = buildDaysOutContext(daysUntilFight);
    const nextKeyGoals = filterAvailablePerformanceFocusValues(currentDaysOutCtx, "key_goals", form.key_goals);
    const nextWeakAreas = filterAvailablePerformanceFocusValues(currentDaysOutCtx, "weak_areas", form.weak_areas);
    if (nextKeyGoals.length === form.key_goals.length && nextWeakAreas.length === form.weak_areas.length) {
      return;
    }

    setForm((current) => ({
      ...current,
      key_goals: filterAvailablePerformanceFocusValues(currentDaysOutCtx, "key_goals", current.key_goals),
      weak_areas: filterAvailablePerformanceFocusValues(currentDaysOutCtx, "weak_areas", current.weak_areas),
    }));
    setMessage("Some picks were removed because they are not available this close to fight day.");
    setError(null);
  }, [daysUntilFight, form.key_goals, form.weak_areas, hydrated]);

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
    return syncDeviceFields(applyNoScheduledFightSnapshot(withGuidedAndCollision, noScheduledFight));
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
      const currentDaysOutCtx = buildDaysOutContext(computeDaysUntilFight(current.fight_date));

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
          message: "Select a technical style before continuing.",
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
        message: "Select a technical style before generating your plan.",
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

  async function persistDraft(step = currentStep) {
    if (!session?.access_token) {
      return;
    }
    const nextForm = buildFormSnapshot();
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
      if (me) {
        replaceMe({
          ...me,
          profile: {
            ...me.profile,
            onboarding_draft: nextDraft,
          },
        });
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
        setError("You must be signed in to save a draft.");
        return;
      }
      try {
        await persistDraft();
        setMessage("Draft saved.");
      } catch (draftError) {
        setError(draftError instanceof Error ? draftError.message : "Unable to save draft.");
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
      try {
        await persistDraft(steps.length - 1);
        markGenerationIntent();
        router.push("/generate");
      } catch (draftError) {
        setError(draftError instanceof Error ? draftError.message : "Unable to prepare plan generation.");
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
  const remainingHardSparringDays = TRAINING_AVAILABILITY_OPTIONS
    .filter((option) => form.training_availability.includes(option.value) && !form.support_work_days.includes(option.value) && !form.hard_sparring_days.includes(option.value))
    .map((option) => option.value);
  const remainingSupportWorkDays = TRAINING_AVAILABILITY_OPTIONS
    .map((option) => option.value)
    .filter((day) => form.training_availability.includes(day) && !form.hard_sparring_days.includes(day));
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
  const weightCutStatus = formatWeightCutStatus(form.athlete.weight_kg, form.athlete.target_weight_kg);
  const equipmentLimitations = formatEquipmentLimitations(form.equipment_access);
  const sparringConsistency = getSparringConsistency(
    form.training_availability,
    form.hard_sparring_days,
    form.support_work_days,
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
    ...(hasValue(form.athlete.target_weight_kg) ? [{ label: "Target weight", value: `${form.athlete.target_weight_kg} kg` }] : []),
    { label: "Stance", value: stanceLabel },
    { label: "Technical style", value: technicalStyleLabel },
    { label: "Tactical style", value: tacticalStyleLabel },
    { label: "Professional status", value: statusLabel },
    { label: "Record", value: formatValue(form.athlete.record) },
  ];
  const campSetupReviewItems = [
    { label: "Fight date", value: formatValue(form.fight_date) },
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
      label: form.athlete.technical_style.length ? "Technical style is selected." : "Technical style must be selected before generation.",
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
              label: form.athlete.technical_style.length ? "Technical style is selected." : "Select at least one technical style.",
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
            <p className="kicker">Advanced Intake</p>
            <h1>Build your camp profile.</h1>
            <p className="muted">Saved, resumable athlete intake.</p>
            <Link href="/quick-build" className="ghost-button onboarding-quick-build-link">
              Use Quick Build instead
            </Link>
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
          <div className="step-layout onboarding-step-layout">
            <div className="step-main athlete-motion-slot athlete-motion-main onboarding-step-main">
              {refiningFromQuickBuild ? (
                <p className="quick-build-refine-notice" role="status">
                  Refining your Quick Build plan. Your existing plan stays until you generate again.
                </p>
              ) : null}
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">Identity</p>
                  <h2 className="form-section-title">Core athlete details</h2>
                </div>
                <div className="form-grid onboarding-profile-grid">
                  <div className="field">
                    <label htmlFor="fullName">Full name</label>
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
                  <div className="field">
                    <label htmlFor="sex">Sex</label>
                    <CustomSelect
                      id="sex"
                      value={form.athlete.sex ?? ""}
                      options={SEX_OPTIONS}
                      placeholder="Select sex"
                      includeEmptyOption
                      onChange={(value) => updateAthlete("sex", (value || null) as PlanRequest["athlete"]["sex"])}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="age">Age</label>
                    <input id="age" type="number" min="0" inputMode="numeric" value={form.athlete.age ?? ""} onChange={(event) => updateAthlete("age", numberOrNull(event.target.value))} />
                  </div>
                  <div className="field">
                    <label htmlFor="weightKg">Weight (kg)</label>
                    <input id="weightKg" type="number" min="0" step="0.1" inputMode="decimal" value={form.athlete.weight_kg ?? ""} onChange={(event) => updateAthlete("weight_kg", numberOrNull(event.target.value))} />
                    <p className="muted">Use current walking-around weight.</p>
                  </div>
                  <div className="field">
                    <label htmlFor="heightCm">Height (cm)</label>
                    <input id="heightCm" type="number" min="0" step="1" inputMode="numeric" value={form.athlete.height_cm ?? ""} onChange={(event) => updateAthlete("height_cm", integerOrNull(event.target.value))} />
                  </div>
                  <div className="field field-span-full">
                    <label htmlFor="stance">Stance</label>
                    <CustomSelect
                      id="stance"
                      value={form.athlete.stance ?? ""}
                      options={STANCE_OPTIONS}
                      placeholder="Select stance"
                      includeEmptyOption
                      onChange={(value) => updateAthlete("stance", value)}
                    />
                  </div>
                </div>
              </article>

              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">Competitive profile</p>
                  <h2 className="form-section-title">Style</h2>
                </div>
                <div className="form-grid onboarding-profile-grid">
                  <div className={`field field-span-full${invalidFieldId === "technicalStyle" ? " field-invalid" : ""}`}>
                    <label htmlFor="technicalStyle">Technical Style</label>
                    <CustomSelect
                      id="technicalStyle"
                      value={form.athlete.technical_style[0] ?? ""}
                      options={TECHNICAL_STYLE_OPTIONS}
                      placeholder="Select technical style"
                      includeEmptyOption
                      invalid={invalidFieldId === "technicalStyle"}
                      describedBy={invalidFieldId === "technicalStyle" ? "technicalStyle-error" : undefined}
                      onChange={(value) => updateAthlete("technical_style", value ? [value] : [])}
                    />
                    <p className="muted">Technical style = your sport or rule set.</p>
                    {invalidFieldId === "technicalStyle" && error ? (
                      <p id="technicalStyle-error" className="error-text" role="alert">{error}</p>
                    ) : null}
                  </div>
                </div>
              </article>

              <OptionalDetails
                title="Add more detail"
                hint="Target weight, tactical style, status, and record. Not required to generate a plan."
              >
                <div className="form-grid onboarding-profile-grid">
                  <div className="field">
                    <label htmlFor="targetWeightKg">Target weight (kg)</label>
                    <input id="targetWeightKg" type="number" min="0" step="0.1" inputMode="decimal" value={form.athlete.target_weight_kg ?? ""} onChange={(event) => updateAthlete("target_weight_kg", numberOrNull(event.target.value))} />
                    <p className="muted">Use realistic fight-week target, not an ideal someday number.</p>
                  </div>
                  <div className="field">
                    <label htmlFor="tacticalStyle">Tactical Style</label>
                    <CustomSelect
                      id="tacticalStyle"
                      value={form.athlete.tactical_style[0] ?? ""}
                      options={TACTICAL_STYLE_OPTIONS}
                      placeholder="Select tactical style"
                      includeEmptyOption
                      onChange={(value) => updateAthlete("tactical_style", value ? [value] : [])}
                    />
                    <p className="muted">Tactical style = how you usually fight inside that sport.</p>
                  </div>
                  <div className="field">
                    <label htmlFor="status">Professional Status</label>
                    <CustomSelect
                      id="status"
                      value={form.athlete.professional_status ?? ""}
                      options={PROFESSIONAL_STATUS_OPTIONS}
                      placeholder="Select professional status"
                      includeEmptyOption
                      onChange={(value) => updateAthlete("professional_status", value)}
                    />
                  </div>
                  <div className={`field${invalidFieldId === "record" || recordHasError ? " field-invalid" : ""}`}>
                    <label htmlFor="record">Record</label>
                    <input
                      id="record"
                      value={form.athlete.record ?? ""}
                      onChange={(event) => updateAthlete("record", sanitizeRecordInput(event.target.value))}
                      placeholder="5-1 or 12-2-1"
                      inputMode="text"
                      maxLength={RECORD_MAX}
                      aria-invalid={invalidFieldId === "record" || recordHasError ? true : undefined}
                      aria-describedby={invalidFieldId === "record" ? "record-error" : undefined}
                    />
                    <p className="muted">Use only <code>x-x</code> or <code>x-x-x</code>.</p>
                    {invalidFieldId === "record" && error ? (
                      <p id="record-error" className="error-text" role="alert">{error}</p>
                    ) : recordHasError ? (
                      <p className="error-text">Enter record as x-x or x-x-x.</p>
                    ) : null}
                  </div>
                </div>
              </OptionalDetails>
            </div>

            <aside className="step-aside athlete-motion-slot athlete-motion-rail onboarding-step-aside">
              <div className="support-panel">
                <div className="form-section-header">
                  <p className="kicker">Profile snapshot</p>
                  <h2 className="form-section-title">Current selections</h2>
                </div>
                <ul className="summary-list">
                  <li>Name: {formatValue(form.athlete.full_name)}</li>
                  <li>Technical Style: {technicalStyleLabel}</li>
                  <li>Tactical Style: {tacticalStyleLabel}</li>
                  <li>Stance: {stanceLabel}</li>
                  <li>Professional Status: {statusLabel}</li>
                  <li>Record: {formatValue(form.athlete.record)}</li>
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
                  <p className="kicker">Fight context</p>
                  <h2 className="form-section-title">Camp timing and load</h2>
                </div>
                <div className="form-grid onboarding-fight-grid">
                  <div className={`field${invalidFieldId === "fightDate" ? " field-invalid" : ""}`}>
                    <label htmlFor="fightDate">Fight date</label>
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
                      <span className="inline-warning-ack-copy">No scheduled fight yet</span>
                    </label>
                    {invalidFieldId === "fightDate" && error ? (
                      <p id="fightDate-error" className="error-text" role="alert">{error}</p>
                    ) : null}
                  </div>
                  <div className={`field${invalidFieldId === "roundCount" ? " field-invalid" : ""}`}>
                    <label htmlFor="roundCount">Round count</label>
                    <CustomSelect
                      id="roundCount"
                      value={parsedRounds.roundCount}
                      options={ROUND_COUNT_OPTIONS}
                      placeholder="Select rounds"
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
                    <label htmlFor="roundDuration">Minutes per round</label>
                    <CustomSelect
                      id="roundDuration"
                      value={parsedRounds.roundDuration}
                      options={ROUND_DURATION_OPTIONS}
                      placeholder="Select minutes"
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
                      <p className="muted" style={{ opacity: 0.5 }}>Weekly session count is not used for planning at this stage.</p>
                    </div>
                  ) : (
                    <div
                      className={`field field-span-full${invalidFieldId === "sessionsPerWeek" ? " field-invalid" : ""}`}
                      style={shouldDeEmphasizeField(daysOutCtx, "weekly_training_frequency") ? { opacity: 0.55 } : undefined}
                    >
                      <label htmlFor="sessionsPerWeek">Planned sessions per week</label>
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
                          "Count the total training sessions the week should carry. Hard sparring days and Light Combat days are labels inside that weekly total, not extra sessions on top."}
                      </p>
                      {invalidFieldId === "sessionsPerWeek" && error ? (
                        <p id="sessionsPerWeek-error" className="error-text" role="alert">{error}</p>
                      ) : null}
                    </div>
                  )}
                </div>
              </article>

              <OptionalDetails
                title="Adjust fatigue level"
                hint="Defaults to Low. Open if you're carrying normal fatigue or noticeably run down right now."
              >
                <div className="field">
                  <label htmlFor="fatigueLevel">Fatigue level</label>
                  <LevelSlider
                    ariaLabel="Fatigue level"
                    value={(form.fatigue_level ?? "low") as LevelValue}
                    onChange={(value) => updateField("fatigue_level", value)}
                  />
                  <p className="muted">Low = fresh, Moderate = carrying normal fatigue, High = noticeably run down.</p>
                </div>
              </OptionalDetails>
            </div>

            <aside className="step-aside athlete-motion-slot athlete-motion-rail onboarding-step-aside">
              <div className="support-panel">
                <div className="form-section-header">
                  <p className="kicker">Context snapshot</p>
                  <h2 className="form-section-title">Current camp setup</h2>
                </div>
                <ul className="summary-list">
                  <li>Fight date: {formatValue(form.fight_date)}</li>
                  <li>Rounds: {formatValue(form.rounds_format)}</li>
                  <li>Planned sessions per week: {formatValue(form.weekly_training_frequency)}</li>
                  <li>Fatigue level: {formatValue(form.fatigue_level || "low")}</li>
                </ul>
              </div>
              <div className="support-panel">
                <p className="kicker">Guidance</p>
                <p className="muted">Fight date and your planned weekly session count shape the camp timeline.</p>
              </div>
            </aside>
          </div>
        ) : null}

        {currentStep === 2 ? (
          <div className="step-layout onboarding-step-layout">
            <div className="step-main athlete-motion-slot athlete-motion-main onboarding-step-main">
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">Schedule</p>
                  <h2 className="form-section-title">Training Availability</h2>
                </div>
                {shouldHideField(daysOutCtx, "training_availability") ? (
                  <div className="field">
                    <p className="muted" style={{ opacity: 0.5 }}>Training availability is not used for planning at this stage.</p>
                  </div>
                ) : (
                <>
                  <CheckboxGroup
                    id="trainingAvailabilityGroup"
                    label="Training Availability"
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
                    <p className="kicker">Consistency check</p>
                    <p className={availabilityConsistency.hardError ? "error-text" : "muted"}>
                      {availabilityConsistency.hardError ?? availabilityConsistency.softWarning}
                    </p>
                  </div>
                ) : null}
              </article>
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">Combat load</p>
                  <h2 className="form-section-title">Sparring and Light Combat day tags</h2>
                </div>
                <p className="muted">
                  These selections do not add extra sessions. They just show which available days are hard-contact days versus
                  Light Combat work inside the same weekly total.
                </p>
                {shouldHideField(daysOutCtx, "hard_sparring_days") ? (
                  <div className="field">
                    <p className="muted" style={{ opacity: 0.5 }}>Hard sparring day selection is not used for planning at this stage.</p>
                  </div>
                ) : (
                <>
                <CheckboxGroup
                  label="Hard Sparring Days"
                  options={TRAINING_AVAILABILITY_OPTIONS}
                  selectedValues={form.hard_sparring_days}
                  onToggle={(value) => toggleFieldValue("hard_sparring_days", value)}
                  disableAll={shouldDisableField(daysOutCtx, "hard_sparring_days")}
                  getOptionDisabledReason={(option, checked) =>
                    checked
                      ? null
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
                      "Pick the days that usually carry the hardest live rounds or highest collision load. These are part of the weekly session total above."}
                  </p>
                  <p className="muted">Available hard sparring tags: {formatJoinedLabels(remainingHardSparringDays, "No days left")}</p>
                </div>
                {hardSparringWarning.message ? (
                  <div
                    id="hardSparringAck"
                    className={`inline-warning-banner ${hardSparringWarningLocked ? "inline-warning-banner-alert" : ""}${invalidFieldId === "hardSparringAck" ? " field-invalid" : ""}`.trim()}
                    tabIndex={invalidFieldId === "hardSparringAck" ? -1 : undefined}
                    aria-invalid={invalidFieldId === "hardSparringAck" ? true : undefined}
                    aria-describedby={invalidFieldId === "hardSparringAck" ? "hardSparringAck-error" : undefined}
                  >
                    <p className="inline-warning-banner-label">High-contact warning</p>
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
                      <span className="inline-warning-ack-copy">I understand this requires deliberate recovery planning.</span>
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
                    <p className="muted" style={{ opacity: 0.5 }}>Light Combat day selection is not used for planning at this stage.</p>
                  </div>
                ) : (
                <>
                <CheckboxGroup
                  label="Light Combat days"
                  options={TRAINING_AVAILABILITY_OPTIONS}
                  selectedValues={form.support_work_days}
                  onToggle={(value) => toggleFieldValue("support_work_days", value)}
                  disableAll={shouldDisableField(daysOutCtx, "support_work_days")}
                  getOptionDisabledReason={(option, checked) =>
                    checked
                      ? null
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
                      "Select days available for lighter work, recovery, technical practice, or S&C. Do not include hard sparring days here."}
                  </p>
                  <p className="muted">Available Light Combat tags: {formatJoinedLabels(remainingSupportWorkDays, "No days left")}</p>
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
                    <p className="kicker">Sparring check</p>
                    <p className={sparringConsistency.hardError ? "error-text" : "muted"}>
                      {sparringConsistency.hardError ?? sparringConsistency.softWarning}
                    </p>
                  </div>
                ) : null}
              </article>
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">Resources</p>
                  <h2 className="form-section-title">Equipment Access</h2>
                </div>
                <CheckboxGroup
                  label="Equipment Access"
                  options={EQUIPMENT_ACCESS_OPTIONS}
                  selectedValues={form.equipment_access}
                  onToggle={(value) => toggleFieldValue("equipment_access", value)}
                />
              </article>
              {shouldHideField(daysOutCtx, "training_preference") ? null : (
              <OptionalDetails
                title="Training preference"
                hint="Tell the planner if you have a specific feel, pace, or format preference for sessions."
              >
                <div className="field" style={shouldDeEmphasizeField(daysOutCtx, "training_preference") ? { opacity: 0.55 } : undefined}>
                  <label htmlFor="trainingPreference">Session preference</label>
                  <textarea
                    id="trainingPreference"
                    disabled={shouldDisableField(daysOutCtx, "training_preference")}
                    value={form.training_preference ?? ""}
                    onChange={(event) => updateField("training_preference", event.target.value)}
                    maxLength={TRAINING_PREFERENCE_MAX}
                    placeholder="Example: shorter hard sessions, less circuit work, more technical warm-ups, avoid long grinders"
                  />
                  <p className="muted">
                    {getFieldHelperText(daysOutCtx, "training_preference") ||
                      "Use this only for session feel, pacing, or format preferences."}
                  </p>
                </div>
              </OptionalDetails>
              )}
            </div>

            <aside className="step-aside athlete-motion-slot athlete-motion-rail onboarding-step-aside">
              <div className="support-panel">
                <div className="form-section-header">
                  <p className="kicker">Current input</p>
                  <h2 className="form-section-title">Selected availability</h2>
                </div>
                <ul className="summary-list">
                  <li>Training Availability: {selectedTrainingAvailability}</li>
                  <li>Hard Sparring Days: {selectedHardSparring}</li>
                  <li>Light Combat days: {selectedSupportWorkDays}</li>
                  <li>Equipment Access: {selectedEquipmentAccess}</li>
                </ul>
              </div>
              <div className="support-panel">
                <p className="kicker">Preference</p>
                <p className="muted">This field is for training feel only, not injuries or general notes.</p>
              </div>
            </aside>
          </div>
        ) : null}

        {currentStep === 3 ? (
          <div className="step-layout onboarding-step-layout onboarding-step-layout-restrictions">
            <div className="step-main athlete-motion-slot athlete-motion-main onboarding-step-main">
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">Restrictions</p>
                  <h2 className="form-section-title">Injuries or restrictions</h2>
                </div>
                {noRestrictions ? (
                  // Empty state — a single inline CTA reveals the body map and a
                  // first card, instead of asking the athlete to untick a box first.
                  <div className="support-panel gi-empty-state compact-gap">
                    <p className="kicker">Anything to train around?</p>
                    <p className="muted">Add any injuries, pain, or movement limits the planner should respect. Leave this empty if there&apos;s nothing to work around.</p>
                    <button type="button" className="injury-card-add-btn" onClick={() => handleNoRestrictionsChange(false)}>
                      <span aria-hidden="true">+</span> Add an injury or restriction
                    </button>
                  </div>
                ) : (
                  <>
                    {reviewRiskInjuryCount > 0 ? (
                      <div className="gi-review-warning gi-review-warning-step" role="status">
                        <svg className="gi-review-warning-icon" width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                          <path d="M8 1.5L1 14h14L8 1.5z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
                          <path d="M8 6v3.5M8 11.5v.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
                        </svg>
                        <div>
                          <strong>
                            {reviewRiskInjuryCount === 1
                              ? "1 injury is flagged for coach review"
                              : `${reviewRiskInjuryCount} injuries are flagged for coach review`}
                          </strong>
                          <span> Serious or medical-safety flags (head impact, heavy bleeding, eye injuries, fractures) may pause planning until a coach signs off. You can still finish — the plan is built around them.</span>
                        </div>
                      </div>
                    ) : null}
                    {showClearInjuriesConfirm ? (
                      <div className="gi-clear-confirm-panel" role="alertdialog" aria-live="polite">
                        <p className="gi-clear-confirm-title">Clear injury cards?</p>
                        <p className="muted">This will remove current injury entries from this intake.</p>
                        <div className="gi-clear-confirm-actions">
                          <button type="button" className="secondary-button" onClick={() => setShowClearInjuriesConfirm(false)}>Keep injuries</button>
                          <button type="button" className="danger-button" onClick={handleConfirmClearInjuries}>Clear injuries</button>
                        </div>
                      </div>
                    ) : null}
                    {pendingInjuryRemovalIndex !== null ? (
                      <div className="gi-clear-confirm-panel" role="alertdialog" aria-live="polite">
                        <p className="gi-clear-confirm-title">
                          Remove {guidedInjuries[pendingInjuryRemovalIndex]?.area || "this injury"}?
                        </p>
                        <p className="muted">This injury has details filled in. Removing will delete them.</p>
                        <div className="gi-clear-confirm-actions">
                          <button type="button" className="secondary-button" onClick={handleCancelRemovePendingInjury}>Keep injury</button>
                          <button type="button" className="danger-button" onClick={handleConfirmRemovePendingInjury}>Remove anyway</button>
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
                            <span aria-hidden="true">+</span> Add another injury
                          </button>
                        </div>
                      </div>
                    </div>
                    <button type="button" className="gi-notes-toggle gi-no-restrictions-btn" onClick={() => handleNoRestrictionsChange(true)}>
                      No current injuries or restrictions
                    </button>
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
                  <p className="focus-cap-label">Focus cap</p>
                  <p className="focus-cap-hint">{performanceFocusCapHint}</p>
                </div>
              </article>
              {shouldHideField(daysOutCtx, "key_goals") ? (
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">Target outcomes</p>
                  <h2 className="form-section-title">Key goals</h2>
                </div>
                <p className="muted" style={{ opacity: 0.5 }}>Goal selection is not used for planning at this stage.</p>
              </article>
              ) : (
              <article className="step-card" style={shouldDeEmphasizeField(daysOutCtx, "key_goals") ? { opacity: 0.55 } : undefined}>
                <div className="form-section-header">
                  <p className="kicker">Target outcomes</p>
                  <h2 className="form-section-title">Key goals</h2>
                </div>
                <CheckboxGroup
                  id="keyGoalsGroup"
                  label="Key Goals"
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
                    <label htmlFor="primaryGoal">Primary goal</label>
                    <CustomSelect
                      id="primaryGoal"
                      value={form.primary_goal ?? ""}
                      options={KEY_GOAL_OPTIONS.filter((option) => form.key_goals.includes(option.value))}
                      placeholder="Select primary goal"
                      includeEmptyOption
                      onChange={(value) => updateField("primary_goal", value)}
                    />
                    <p className="muted">Pick which one the plan should be built around.</p>
                  </div>
                ) : null}
              </article>
              )}
              {shouldHideField(daysOutCtx, "weak_areas") ? (
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">Performance gaps</p>
                  <h2 className="form-section-title">Weak areas</h2>
                </div>
                <p className="muted" style={{ opacity: 0.5 }}>Weak area selection is not used for planning at this stage.</p>
              </article>
              ) : (
              <article className="step-card" style={shouldDeEmphasizeField(daysOutCtx, "weak_areas") ? { opacity: 0.55 } : undefined}>
                <div className="form-section-header">
                  <p className="kicker">Performance gaps</p>
                  <h2 className="form-section-title">Weak areas</h2>
                </div>
                <CheckboxGroup
                  label="Weak Areas"
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
                    <label htmlFor="primaryWeakArea">Primary weak area</label>
                    <CustomSelect
                      id="primaryWeakArea"
                      value={form.primary_weak_area ?? ""}
                      options={WEAK_AREA_OPTIONS.filter((option) => form.weak_areas.includes(option.value))}
                      placeholder="Select primary weak area"
                      includeEmptyOption
                      onChange={(value) => updateField("primary_weak_area", value)}
                    />
                    <p className="muted">Pick which one the plan must manage first.</p>
                  </div>
                ) : null}
                <p className="muted">Pick up to 2 weak areas.</p>
              </article>
              )}
              {goalWeakAreaOverlaps.length ? (
                <article className="step-card priority-clarification-card">
                  <div className="form-section-header">
                    <p className="kicker">Clarification</p>
                    <h2 className="form-section-title">Priority detail</h2>
                  </div>
                  <div className="priority-clarification-copy">
                    <p>{overlapClarificationPrompt}</p>
                    <p className="muted">Optional. This helps capture intent without changing your selected goal or weak area.</p>
                  </div>
                  <div className="priority-clarification-options" role="radiogroup" aria-label="Goal and weak area clarification">
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
                title="Add coach notes"
                hint="Mental / confidence issues, or anything else the planner should know."
              >
                <div className="form-grid">
                  <div className="field">
                    <label htmlFor="mindsetChallenges">Mental / confidence issue</label>
                    <textarea
                      id="mindsetChallenges"
                      value={form.mindset_challenges ?? ""}
                      onChange={(event) => updateField("mindset_challenges", event.target.value)}
                      maxLength={MENTAL_BLOCKERS_MAX}
                      placeholder="Optional: anxiety under pressure, low confidence late in camp, trouble switching on"
                    />
                    <p className="muted">Only use this if there is a real mental or confidence issue the plan should respect.</p>
                  </div>
                  <div className="field">
                    <label htmlFor="notes">Anything else we should know?</label>
                    <textarea
                      id="notes"
                      value={form.notes ?? ""}
                      onChange={(event) => updateField("notes", event.target.value)}
                      maxLength={PREVIOUS_PLAN_FEEDBACK_MAX}
                      placeholder="Optional: travel, school/work load, sparring schedule, recovery issue, or anything else the planner should know"
                    />
                    <p className="muted">Use this for extra coach context that does not fit the other fields.</p>
                  </div>
                </div>
              </OptionalDetails>
            </div>

            <aside className="step-aside athlete-motion-slot athlete-motion-rail onboarding-step-aside">
              <div className="support-panel">
                <div className="form-section-header">
                  <p className="kicker">Performance snapshot</p>
                  <h2 className="form-section-title">Selected focus</h2>
                </div>
                <ul className="summary-list">
                  <li>Key Goals: {selectedGoals}</li>
                  <li>Weak Areas: {selectedWeakAreas}</li>
                  <li>Mental / confidence issue: {formatValue(form.mindset_challenges)}</li>
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
                  <p className="kicker">Review</p>
                  <h2 className="form-section-title">Captured athlete input</h2>
                </div>
                <div className="review-columns">
                  <div className="review-column">
                    <article className="review-card">
                      <div className="review-card-header">
                        <p className="kicker">Profile</p>
                        <h3 className="review-card-title">Athlete profile</h3>
                      </div>
                      <ReviewDetailList items={profileReviewItems} />
                    </article>
                    <article className="review-card">
                      <div className="review-card-header">
                        <p className="kicker">Training</p>
                        <h3 className="review-card-title">Availability and equipment</h3>
                      </div>
                      <ReviewDetailList items={trainingReviewItems} />
                    </article>
                  </div>
                  <div className="review-column">
                    <article className="review-card">
                      <div className="review-card-header">
                        <p className="kicker">Fight context</p>
                        <h3 className="review-card-title">Camp setup</h3>
                      </div>
                      <ReviewDetailList items={campSetupReviewItems} />
                    </article>
                    <article className="review-card">
                      <div className="review-card-header">
                        <p className="kicker">Performance</p>
                        <h3 className="review-card-title">Goals and weak areas</h3>
                      </div>
                      <ReviewDetailList items={performanceReviewItems} />
                    </article>
                    <article className="review-card">
                      <div className="review-card-header">
                        <p className="kicker">Constraints</p>
                        <h3 className="review-card-title">Constraints and risks</h3>
                      </div>
                      <ReviewDetailList items={constraintsReviewItems} />
                    </article>
                  </div>
                </div>
              </article>
            </div>

            <aside className="step-aside athlete-motion-slot athlete-motion-rail onboarding-step-aside">
              <div className="support-panel">
                <p className="kicker">Restrictions</p>
                <p className="muted">Injuries or restrictions: {restrictionSummary}</p>
              </div>
              <div className="support-panel">
                <p className="kicker">Nutrition foundation</p>
                <p className="muted">Weight setup, bodyweight logging, and readiness fields now live in the dedicated nutrition workspace.</p>
                <div className="plan-summary-actions">
                  <Link href="/nutrition" className="ghost-button">
                    Open nutrition workspace
                  </Link>
                </div>
              </div>
            </aside>
          </div>
        ) : null}

        {message ? <div className="success-banner athlete-motion-slot athlete-motion-status">{message}</div> : null}
        {error ? (
          <div
            id="onboarding-error-banner"
            className="error-banner athlete-motion-slot athlete-motion-status"
            role="alert"
            aria-live="assertive"
          >
            {error}
          </div>
        ) : null}

        <div className="form-actions onboarding-action-bar athlete-motion-slot athlete-motion-rail">
          <div className="onboarding-action-bar-copy">
            <p className="kicker">{actionBarTitle}</p>
            <p className="muted">{actionBarSummary}</p>
          </div>
          <div className="onboarding-action-buttons">
            <button type="button" className="ghost-button onboarding-action-secondary" onClick={handleSaveDraft} disabled={formActionPending}>
              {isPending ? "Saving..." : "Save draft"}
            </button>
            {currentStep > 0 ? (
              <button type="button" className="ghost-button onboarding-action-secondary" onClick={handleBack}>
                Back
              </button>
            ) : null}
            {currentStep < steps.length - 1 ? (
              <button type="button" className="cta onboarding-action-primary" onClick={handleNext} disabled={formActionPending}>
                Continue
              </button>
            ) : (
              <>
                <button type="button" className="cta onboarding-action-primary" onClick={handleGenerate} disabled={formActionPending}>
                  Generate plan
                </button>
              </>
            )}
          </div>
        </div>
      </section>
    </RequireAuth>
  );
}
