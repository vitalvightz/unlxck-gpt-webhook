"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { BodyMap, type BodyMapSide } from "@/components/body-map";
import { CustomSelect } from "@/components/custom-select";
import { generateStage1Preview, updateMe } from "@/lib/api";
import {
  detectDeviceTimeZone,
  EQUIPMENT_ACCESS_OPTIONS,
  getOptionLabel,
  getOptionLabels,
  isValidRecordFormat,
  KEY_GOAL_OPTIONS,
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
import { emptyPlanRequest, hydratePlanRequest, mergePlanRequestDraft } from "@/lib/onboarding";
import { buildRoundsFormat, parseRoundsFormat, ROUND_COUNT_OPTIONS, ROUND_DURATION_OPTIONS } from "@/lib/rounds-format";
import { getPerformanceFocusCap, validatePerformanceFocusSelections } from "@/lib/performance-focus-cap";
import { canSelectWizardStep } from "@/lib/step-navigation";
import {
  getAvailabilityConsistency,
  getHardSparringWarning,
  getSparringConsistency,
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
import type { PlanRequest, Stage1PreviewResponse } from "@/lib/types";

const steps = ["Profile", "Fight Context", "Training", "Restrictions", "Performance", "Review"] as const;
const PERFORMANCE_STEP_INDEX = 4;
const SEX_OPTIONS: IntakeOption[] = [
  { label: "Male", value: "male" },
  { label: "Female", value: "female" },
];
const FATIGUE_LEVEL_OPTIONS = [
  { label: "Low", value: "low" },
  { label: "Moderate", value: "moderate" },
  { label: "High", value: "high" },
];

type DraftMetadata = {
  current_step?: number;
  guided_injury?: Partial<GuidedInjuryState> | null;
  guided_injuries?: Array<Partial<GuidedInjuryState> | null> | null;
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
    <div className="step-progress" aria-label="Onboarding progress">
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
        ? "All onboarding steps are complete. Review your answers, then generate the plan."
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
        <p className="kicker">Onboarding progress</p>
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
      <div ref={railRef} className="mobile-step-rail-scroll" aria-label="Onboarding steps">
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
        <p className="kicker">Athlete Onboarding</p>
        <p className="onboarding-mobile-title">Build your camp profile.</p>
        <p className="muted">Saved, resumable athlete intake.</p>
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
  label,
  options,
  selectedValues,
  onToggle,
  disableAdditionalSelections = false,
  disableAll = false,
  getOptionDisabledReason,
}: {
  label: string;
  options: IntakeOption[];
  selectedValues: string[];
  onToggle: (value: string) => void;
  disableAdditionalSelections?: boolean;
  disableAll?: boolean;
  getOptionDisabledReason?: (option: IntakeOption, checked: boolean) => string | null;
}) {
  return (
    <div className="field">
      <span className="checkbox-group-label">{label}</span>
      <div className="checkbox-grid">
        {options.map((option) => {
          const checked = selectedValues.includes(option.value);
          const daysOutDisabledReason = getOptionDisabledReason?.(option, checked) ?? null;
          const capDisabled = disableAdditionalSelections && !checked;
          const disabled = disableAll || Boolean(daysOutDisabledReason) || capDisabled;
          const labelTitle = daysOutDisabledReason ?? (capDisabled ? "Focus cap reached." : undefined);
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
              </span>
            </label>
          );
        })}
      </div>
    </div>
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
  },
): { message: string; step: number } | null {
  if (!isValidRecordFormat(nextForm.athlete.record ?? "")) return { message: "Record must use x-x or x-x-x format, like 5-1 or 12-2-1.", step: 0 };
  if (!nextForm.athlete.technical_style.length) return { message: "Select a technical style before continuing to review.", step: 0 };
  if (!nextForm.fight_date) return { message: "Choose your fight date before continuing to review.", step: 1 };
  if (!nextForm.training_availability.length) return { message: "Pick at least one training availability option before continuing to review.", step: 2 };
  if (!nextForm.weekly_training_frequency || nextForm.weekly_training_frequency < 1) return { message: "Planned sessions per week must be at least 1.", step: 1 };
  if (nextForm.weekly_training_frequency > 6) return { message: "Planned sessions per week cannot exceed 6.", step: 1 };
  const parsedRounds = parseRoundsFormat(nextForm.rounds_format);
  if (!parsedRounds.roundCount || !parsedRounds.roundDuration) return { message: "Choose both round count and round duration before continuing to review.", step: 1 };
  if (options.hardSparringWarningLocked) {
    return { message: "Acknowledge the hard sparring warning in the Training step before continuing to review.", step: 2 };
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
  | { kind: "hard_error"; message: string }
  | { kind: "warning_ack_required"; message: string; shouldRedirectToTraining: boolean };

export function PlanIntakeForm() {
  const router = useRouter();
  const { me, replaceMe, session } = useAppSession();
  const [currentStep, setCurrentStep] = useState(0);
  const [isMobileProgressOpen, setIsMobileProgressOpen] = useState(false);
  const [form, setForm] = useState<PlanRequest>(emptyPlanRequest());
  const [guidedInjuries, setGuidedInjuries] = useState<GuidedInjuryState[]>([]);
  const [activeGuidedInjuryIndex, setActiveGuidedInjuryIndex] = useState<number | null>(null);
  const [noRestrictions, setNoRestrictions] = useState(true);
  const [showClearInjuriesConfirm, setShowClearInjuriesConfirm] = useState(false);
  const [bodyMapSide, setBodyMapSide] = useState<BodyMapSide>("front");
  const [hydrated, setHydrated] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stage1Preview, setStage1Preview] = useState<Stage1PreviewResponse | null>(null);
  const [stage1PreviewPending, setStage1PreviewPending] = useState(false);
  const [isPending, startTransition] = useTransition();
  const [acknowledgedHardSparringWarningKey, setAcknowledgedHardSparringWarningKey] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [lastSavedAt, setLastSavedAt] = useState<number | null>(null);
  const lastSavedSnapshotRef = useRef<string>("");
  const issueRedirectConsumedRef = useRef(false);
  const recordHasError = !isValidRecordFormat(form.athlete.record ?? "");

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
    const savedStep = Number(draft?.current_step ?? 0);
    setCurrentStep(Number.isFinite(savedStep) ? Math.min(Math.max(savedStep, 0), steps.length - 1) : 0);
    setHydrated(true);
  }, [hydrated, me]);

  useEffect(() => {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reducedMotion ? "instant" : "smooth" });
  }, [currentStep]);

  useEffect(() => {
    if (!stage1Preview || currentStep !== steps.length - 1) {
      return;
    }

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.setTimeout(() => {
      document.getElementById("stage1-preview")?.scrollIntoView({
        behavior: reducedMotion ? "instant" : "smooth",
        block: "start",
      });
    }, 0);
  }, [currentStep, stage1Preview]);

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
      } else if (!selectedGoals.includes(current.primary_goal ?? "")) {
        next.primary_goal = "";
        changed = true;
      }

      if (selectedWeakAreas.length === 1) {
        const onlyWeakArea = selectedWeakAreas[0];
        if (current.primary_weak_area !== onlyWeakArea) {
          next.primary_weak_area = onlyWeakArea;
          changed = true;
        }
      } else if (!selectedWeakAreas.includes(current.primary_weak_area ?? "")) {
        next.primary_weak_area = "";
        changed = true;
      }

      return changed ? next : current;
    });
  }, [form.key_goals, form.primary_goal, form.primary_weak_area, form.weak_areas]);


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
    return syncDeviceFields({
      ...currentForm,
      ...nextGuidedInjuryFields,
    });
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

  function handleBodyMapZoneSelect(label: string) {
    const existingIndex = guidedInjuries.findIndex((injury) => injury.area.toLowerCase() === label.toLowerCase());
    if (existingIndex >= 0) {
      setActiveGuidedInjuryIndex(existingIndex);
      return;
    }

    const emptyIndex = guidedInjuries.findIndex((injury) => !injury.area.trim());
    if (emptyIndex >= 0) {
      updateGuidedInjury(emptyIndex, "area", label);
      setActiveGuidedInjuryIndex(emptyIndex);
      return;
    }

    const nextGuidedInjuries = [...guidedInjuries, { ...EMPTY_GUIDED_INJURY, area: label }];
    syncGuidedInjuryFields(nextGuidedInjuries, false);
    setActiveGuidedInjuryIndex(nextGuidedInjuries.length - 1);
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

      return {
        ...current,
        [key]: toggleListValue(currentValues, value),
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

    if (decision.kind === "warning_ack_required" && decision.shouldRedirectToTraining) {
      setCurrentStep(2);
      setIsMobileProgressOpen(true);
    }

    setError(decision.message);
    return false;
  }

  function validateCurrentStep(
    nextForm: PlanRequest,
    action: TrainingGateAction = "next",
    targetStep?: number,
  ): boolean {
    if (currentStep === 0 && !isValidRecordFormat(nextForm.athlete.record ?? "")) {
      setError("Record must use x-x or x-x-x format, like 5-1 or 12-2-1.");
      return false;
    }
    if (currentStep === 1) {
      const parsedRounds = parseRoundsFormat(nextForm.rounds_format);
      if (!parsedRounds.roundCount || !parsedRounds.roundDuration) {
        setError("Choose both round count and round duration before continuing.");
        return false;
      }
    }
    if (currentStep === 3 && (nextForm.guided_injuries ?? []).some((injury) => hasGuidedInjuryDescriptorWithoutArea(injury))) {
      setError("Add a pain area or body part before choosing severity or trend.");
      return false;
    }
    if (currentStep === PERFORMANCE_STEP_INDEX) {
      const focusValidation = validatePerformanceFocusSelections(
        nextForm.fight_date,
        { keyGoals: nextForm.key_goals, weakAreas: nextForm.weak_areas },
        { timeZone: nextForm.athlete.athlete_timezone },
      );
      if (focusValidation.isOverCap) {
        setError(focusValidation.errorMessage);
        return false;
      }
    }
    return applyTrainingGate(nextForm, action, targetStep);
  }

  function validateForGeneration(nextForm: PlanRequest): boolean {
    if (!validateCurrentStep(nextForm, "generate")) {
      return false;
    }
    if (!nextForm.athlete.technical_style.length) {
      setError("Select a technical style before generating your plan.");
      return false;
    }
    if (!nextForm.fight_date) {
      setError("Choose your fight date before generating your plan.");
      return false;
    }
    if (!nextForm.training_availability.length) {
      setError("Pick at least one training availability option before generating your plan.");
      return false;
    }
    if (!nextForm.weekly_training_frequency || nextForm.weekly_training_frequency < 1) {
    setError("Planned sessions per week must be at least 1.");
      return false;
    }
    if (nextForm.weekly_training_frequency > 6) {
    setError("Planned sessions per week cannot exceed 6.");
      return false;
    }
    const parsedRounds = parseRoundsFormat(nextForm.rounds_format);
    if (!parsedRounds.roundCount || !parsedRounds.roundDuration) {
      setError("Choose both round count and round duration before generating your plan.");
      return false;
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
      setCurrentStep(PERFORMANCE_STEP_INDEX);
      setIsMobileProgressOpen(true);
      setError(focusValidation.errorMessage);
      return false;
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
      const updatedMe = await updateMe(session.access_token, {
        full_name: nextForm.athlete.full_name,
        technical_style: nextForm.athlete.technical_style,
        tactical_style: nextForm.athlete.tactical_style,
        stance: nextForm.athlete.stance,
        professional_status: nextForm.athlete.professional_status,
        record: nextForm.athlete.record,
        athlete_timezone: nextForm.athlete.athlete_timezone,
        onboarding_draft: {
          ...mergePlanRequestDraft(me?.profile.onboarding_draft as Record<string, unknown> | null | undefined, nextForm, step),
        },
      });
      replaceMe(updatedMe);
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
    setCurrentStep((step) => Math.max(step - 1, 0));
    setIsMobileProgressOpen(false);
  }

  function handleStepSelect(targetStep: number) {
    setMessage(null);
    setError(null);
    let nextForm: PlanRequest | null = null;
    function getNextForm() {
      nextForm ??= buildFormSnapshot();
      return nextForm;
    }
    if (targetStep === steps.length - 1 && targetStep > currentStep) {
      const reviewIssue = getReviewStepBlockingIssue(getNextForm(), {
        hardSparringWarningLocked,
      });
      if (reviewIssue) {
        setError(reviewIssue.message);
        setCurrentStep(reviewIssue.step);
        setIsMobileProgressOpen(true);
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
    startTransition(async () => {
      const nextForm = buildFormSnapshot();
      if (!validateForGeneration(nextForm)) {
        return;
      }
      try {
        await persistDraft(steps.length - 1);
        router.push("/generate");
      } catch (draftError) {
        setError(draftError instanceof Error ? draftError.message : "Unable to prepare plan generation.");
      }
    });
  }

  function handleGenerateStage1Preview() {
    setMessage(null);
    setError(null);
    setStage1Preview(null);
    startTransition(async () => {
      const nextForm = buildFormSnapshot();
      if (!validateForGeneration(nextForm)) {
        return;
      }
      if (!session?.access_token) {
        setError("You must be signed in to generate a Stage 1 preview.");
        return;
      }

      setStage1PreviewPending(true);
      try {
        await persistDraft(steps.length - 1);
        const preview = await generateStage1Preview(session.access_token, nextForm);
        setStage1Preview(preview);
        setMessage("Stage 1 preview generated. Stage 2 was not run.");
      } catch (previewError) {
        setError(previewError instanceof Error ? previewError.message : "Unable to generate Stage 1 preview.");
      } finally {
        setStage1PreviewPending(false);
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
  const selectedSupportWorkDays = formatJoinedLabels(selectedSupportWorkLabels, "No non-hard training days selected");
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
    fatigueLevel: form.fatigue_level || "moderate",
    injuries: form.injuries || "",
    sessionsPerWeek: form.weekly_training_frequency,
    technicalStyle: form.athlete.technical_style[0] ?? "",
    hardSparringDays: selectedHardSparringLabels,
  });
  const highFatigueFlag = (form.fatigue_level || "moderate") === "high" ? "High fatigue already reported" : null;
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
    { label: "Fatigue level", value: formatValue(form.fatigue_level || "moderate") },
  ];
  const trainingReviewItems = [
    { label: "Training availability", value: selectedTrainingAvailability },
    { label: "Hard sparring days", value: selectedHardSparring },
    { label: "Non-hard training days", value: selectedSupportWorkDays },
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
      label: form.fight_date ? "Fight date is set." : "Fight date must be set before generation.",
      status: form.fight_date ? "done" : "pending",
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
              label: form.fight_date ? "Fight date is set." : "Choose the fight date.",
              status: form.fight_date ? "done" : "pending",
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
  const formActionPending = isPending || stage1PreviewPending;

  return (
    <RequireAuth>
      <section className="panel onboarding-panel">
        <div className="section-heading onboarding-heading-desktop">
          <div className="athlete-motion-slot athlete-motion-header">
            <p className="kicker">Athlete Onboarding</p>
            <h1>Build your camp profile.</h1>
            <p className="muted">Saved, resumable athlete intake.</p>
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
                    <label htmlFor="targetWeightKg">Target weight (kg)</label>
                    <input id="targetWeightKg" type="number" min="0" step="0.1" inputMode="decimal" value={form.athlete.target_weight_kg ?? ""} onChange={(event) => updateAthlete("target_weight_kg", numberOrNull(event.target.value))} />
                    <p className="muted">Use realistic fight-week target, not an ideal someday number.</p>
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
                  <h2 className="form-section-title">Style and status</h2>
                </div>
                <div className="form-grid onboarding-profile-grid">
                  <div className="field">
                    <label htmlFor="technicalStyle">Technical Style</label>
                    <CustomSelect
                      id="technicalStyle"
                      value={form.athlete.technical_style[0] ?? ""}
                      options={TECHNICAL_STYLE_OPTIONS}
                      placeholder="Select technical style"
                      includeEmptyOption
                      onChange={(value) => updateAthlete("technical_style", value ? [value] : [])}
                    />
                    <p className="muted">Technical style = your sport or rule set.</p>
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
                  <div className="field">
                    <label htmlFor="record">Record</label>
                    <input
                      id="record"
                      value={form.athlete.record ?? ""}
                      onChange={(event) => updateAthlete("record", sanitizeRecordInput(event.target.value))}
                      placeholder="5-1 or 12-2-1"
                      inputMode="text"
                    />
                    <p className="muted">Use only <code>x-x</code> or <code>x-x-x</code>.</p>
                    {recordHasError ? <p className="error-text">Enter record as x-x or x-x-x.</p> : null}
                  </div>
                </div>
              </article>
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
                  <div className="field">
                    <label htmlFor="fightDate">Fight date</label>
                    <input id="fightDate" type="date" min={getTodayIsoDate()} value={form.fight_date} onChange={(event) => updateField("fight_date", event.target.value)} />
                  </div>
                  <div className="field">
                    <label htmlFor="roundCount">Round count</label>
                    <CustomSelect
                      id="roundCount"
                      value={parsedRounds.roundCount}
                      options={ROUND_COUNT_OPTIONS}
                      placeholder="Select rounds"
                      includeEmptyOption
                      onChange={(value) => updateRoundsField("roundCount", value)}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="roundDuration">Minutes per round</label>
                    <CustomSelect
                      id="roundDuration"
                      value={parsedRounds.roundDuration}
                      options={ROUND_DURATION_OPTIONS}
                      placeholder="Select minutes"
                      includeEmptyOption
                      onChange={(value) => updateRoundsField("roundDuration", value)}
                    />
                  </div>
                  <div className="field">
                    <label htmlFor="fatigueLevel">Fatigue level</label>
                    <CustomSelect
                      id="fatigueLevel"
                      value={form.fatigue_level ?? "moderate"}
                      options={FATIGUE_LEVEL_OPTIONS}
                      placeholder="Select fatigue level"
                      onChange={(value) => updateField("fatigue_level", value)}
                    />
                    <p className="muted">Low = fresh, Moderate = carrying normal fatigue, High = noticeably run down.</p>
                  </div>
                  {shouldHideField(daysOutCtx, "weekly_training_frequency") ? (
                    <div className="field field-span-full">
                      <p className="muted" style={{ opacity: 0.5 }}>Weekly session count is not used for planning at this stage.</p>
                    </div>
                  ) : (
                    <div
                      className="field field-span-full"
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
                      />
                      <p className="muted">
                        {getFieldHelperText(daysOutCtx, "weekly_training_frequency") ||
                          "Count the total training sessions the week should carry. Hard sparring days and non-hard training days are labels inside that weekly total, not extra sessions on top."}
                      </p>
                    </div>
                  )}
                </div>
              </article>
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
                  <li>Fatigue level: {formatValue(form.fatigue_level || "moderate")}</li>
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
              {availabilityConsistency.hardError || availabilityConsistency.softWarning ? (
                <div className={`support-panel ${availabilityConsistency.hardError ? "support-panel-alert" : ""}`.trim()}>
                  <p className="kicker">Consistency check</p>
                  <p className={availabilityConsistency.hardError ? "error-text" : "muted"}>
                    {availabilityConsistency.hardError ?? availabilityConsistency.softWarning}
                  </p>
                </div>
              ) : null}
              {sparringConsistency.hardError || sparringConsistency.softWarning ? (
                <div className={`support-panel ${sparringConsistency.hardError ? "support-panel-alert" : ""}`.trim()}>
                  <p className="kicker">Sparring check</p>
                  <p className={sparringConsistency.hardError ? "error-text" : "muted"}>
                    {sparringConsistency.hardError ?? sparringConsistency.softWarning}
                  </p>
                </div>
              ) : null}
              {hardSparringWarning.message ? (
                <div className={`inline-warning-banner ${hardSparringWarningLocked ? "inline-warning-banner-alert" : ""}`.trim()}>
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
                </div>
              ) : null}
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
                <CheckboxGroup
                  label="Training Availability"
                  options={TRAINING_AVAILABILITY_OPTIONS}
                  selectedValues={form.training_availability}
                  onToggle={(value) => toggleFieldValue("training_availability", value)}
                  disableAll={shouldDisableField(daysOutCtx, "training_availability")}
                />
                )}
              </article>
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">Combat load</p>
                  <h2 className="form-section-title">Sparring and non-hard day tags</h2>
                </div>
                <p className="muted">
                  These selections do not add extra sessions. They just show which available days are hard-contact days versus
                  non-hard work inside the same weekly total.
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
                />
                <div className="field">
                  <p className="muted">
                    {getFieldHelperText(daysOutCtx, "hard_sparring_days") ||
                      "Pick the days that usually carry the hardest live rounds or highest collision load. These are part of the weekly session total above."}
                  </p>
                </div>
                </>
                )}
                {shouldHideField(daysOutCtx, "support_work_days") ? (
                  <div className="field">
                    <p className="muted" style={{ opacity: 0.5 }}>Non-hard training day selection is not used for planning at this stage.</p>
                  </div>
                ) : (
                <>
                <CheckboxGroup
                  label="Non-hard training days"
                  options={TRAINING_AVAILABILITY_OPTIONS}
                  selectedValues={form.support_work_days}
                  onToggle={(value) => toggleFieldValue("support_work_days", value)}
                  disableAll={shouldDisableField(daysOutCtx, "support_work_days")}
                />
                <div className="field">
                  <p className="muted">
                    {getFieldHelperText(daysOutCtx, "support_work_days") ||
                      "Select days available for lighter work, recovery, technical practice, or S&C. Do not include hard sparring days here."}
                  </p>
                </div>
                </>
                )}
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
              <article className="step-card" style={shouldDeEmphasizeField(daysOutCtx, "training_preference") ? { opacity: 0.55 } : undefined}>
                <div className="form-section-header">
                  <p className="kicker">Training style</p>
                  <h2 className="form-section-title">Training Preference</h2>
                </div>
                  <div className="field">
                    <label htmlFor="trainingPreference">Session preference</label>
                    <textarea
                      id="trainingPreference"
                      disabled={shouldDisableField(daysOutCtx, "training_preference")}
                      value={form.training_preference ?? ""}
                      onChange={(event) => updateField("training_preference", event.target.value)}
                      placeholder="Example: shorter hard sessions, less circuit work, more technical warm-ups, avoid long grinders"
                    />
                    <p className="muted">
                      {getFieldHelperText(daysOutCtx, "training_preference") ||
                        "Use this only for session feel, pacing, or format preferences."}
                    </p>
                  </div>
              </article>
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
                  <li>Non-hard training days: {selectedSupportWorkDays}</li>
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
                <label className={`inline-warning-ack inline-warning-ack-compact ${noRestrictions ? "inline-warning-ack-checked" : ""}`.trim()}>
                  <input
                    type="checkbox"
                    checked={noRestrictions}
                    onChange={(event) => handleNoRestrictionsChange(event.target.checked)}
                  />
                  <span className="inline-warning-ack-stack">
                    <span className="inline-warning-ack-copy">No current injuries or restrictions</span>
                    <span className="muted">Leave this checked when the athlete has nothing the planner needs to work around.</span>
                  </span>
                </label>
                {!noRestrictions ? (
                  <>
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
                    <div className="injury-body-map-layout">
                      <div className="injury-body-map-col">
                        <BodyMap
                          side={bodyMapSide}
                          selections={guidedInjuries
                            .filter((injury) => injury.area.trim())
                            .map((injury) => ({
                              label: injury.area,
                              severity: normalizeGuidedInjurySeverity(injury.severity) || undefined,
                            }))}
                          onZoneSelect={handleBodyMapZoneSelect}
                          onSideChange={setBodyMapSide}
                        />
                      </div>
                      <div className="injury-cards-col">
                        <div className="injury-card-stack">
                          {guidedInjuries.map((injury, index) => (
                            <GuidedInjuryCard
                              key={`guided-injury-${index}`}
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
                              onRemove={() => handleRemoveGuidedInjury(index)}
                            />
                          ))}
                        </div>

                        <div className="injury-card-add-row">
                          <button type="button" className="injury-card-add-btn" onClick={handleAddGuidedInjury}>
                            <span aria-hidden="true">+</span> Add another injury
                          </button>
                        </div>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="support-panel gi-empty-state compact-gap">
                    <p className="kicker">No current injuries selected</p>
                    <p className="muted">The planner will not add injury restrictions unless you add one.</p>
                    <button type="button" className="injury-card-add-btn" onClick={() => handleNoRestrictionsChange(false)}>Add injury or restriction</button>
                  </div>
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
                  label="Key Goals"
                  options={KEY_GOAL_OPTIONS}
                  selectedValues={form.key_goals}
                  onToggle={(value) => toggleFieldValue("key_goals", value)}
                  disableAdditionalSelections={performanceFocusCapReached}
                  disableAll={shouldDisableField(daysOutCtx, "key_goals")}
                  getOptionDisabledReason={getKeyGoalDisabledReason}
                />
                {getFieldHelperText(daysOutCtx, "key_goals") ? (
                  <p className="muted">{getFieldHelperText(daysOutCtx, "key_goals")}</p>
                ) : null}
                {form.key_goals.length ? (
                  <div className="field">
                    <label htmlFor="primaryGoal">Primary goal</label>
                    <CustomSelect
                      id="primaryGoal"
                      value={form.primary_goal ?? ""}
                      options={KEY_GOAL_OPTIONS.filter((option) => form.key_goals.includes(option.value))}
                      placeholder="Select primary goal"
                      includeEmptyOption={form.key_goals.length > 1}
                      onChange={(value) => updateField("primary_goal", value)}
                    />
                    <p className="muted">This is what the plan should be built around.</p>
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
                  disableAll={shouldDisableField(daysOutCtx, "weak_areas")}
                  getOptionDisabledReason={getWeakAreaDisabledReason}
                />
                {getFieldHelperText(daysOutCtx, "weak_areas") ? (
                  <p className="muted">{getFieldHelperText(daysOutCtx, "weak_areas")}</p>
                ) : null}
                {form.weak_areas.length ? (
                  <div className="field">
                    <label htmlFor="primaryWeakArea">Primary weak area</label>
                    <CustomSelect
                      id="primaryWeakArea"
                      value={form.primary_weak_area ?? ""}
                      options={WEAK_AREA_OPTIONS.filter((option) => form.weak_areas.includes(option.value))}
                      placeholder="Select primary weak area"
                      includeEmptyOption={form.weak_areas.length > 1}
                      onChange={(value) => updateField("primary_weak_area", value)}
                    />
                    <p className="muted">This is the main limiter the plan must manage.</p>
                  </div>
                ) : null}
                <p className="muted">Pick up to 2 weak areas.</p>
              </article>
              )}
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">Extra context</p>
                  <h2 className="form-section-title">Optional coach notes</h2>
                </div>
                <div className="form-grid">
                  <div className="field">
                    <label htmlFor="mindsetChallenges">Mental / confidence issue</label>
                    <textarea
                      id="mindsetChallenges"
                      value={form.mindset_challenges ?? ""}
                      onChange={(event) => updateField("mindset_challenges", event.target.value)}
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
                      placeholder="Optional: travel, school/work load, sparring schedule, recovery issue, or anything else the planner should know"
                    />
                    <p className="muted">Use this for extra coach context that does not fit the other fields.</p>
                  </div>
                </div>
              </article>
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
              {stage1Preview ? (
                <article id="stage1-preview" className="step-card">
                  <div className="form-section-header">
                    <p className="kicker">Stage 1 only</p>
                    <h2 className="form-section-title">Planner draft before Stage 2</h2>
                    <p className="muted">
                      Generated {new Date(stage1Preview.generated_at).toLocaleString()}. Stage 2 was skipped.
                    </p>
                  </div>
                  <pre className="plan-text-block">
                    {stage1Preview.plan_text || "No Stage 1 draft text returned."}
                  </pre>
                  <div className="plan-summary-actions">
                    <button type="button" className="ghost-button" onClick={() => setStage1Preview(null)}>
                      Clear preview
                    </button>
                  </div>
                </article>
              ) : null}
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
        {error ? <div className="error-banner athlete-motion-slot athlete-motion-status">{error}</div> : null}

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
                <button
                  type="button"
                  className="ghost-button onboarding-action-secondary onboarding-action-stage1"
                  onClick={handleGenerateStage1Preview}
                  disabled={formActionPending}
                >
                  {stage1PreviewPending ? "Generating Stage 1..." : "Generate Stage 1 only"}
                </button>
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
