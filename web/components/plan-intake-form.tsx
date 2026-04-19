"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { BodyMap, type BodyMapSide } from "@/components/body-map";
import { CustomSelect } from "@/components/custom-select";
import { updateMe } from "@/lib/api";
import {
  detectDeviceTimeZone,
  EQUIPMENT_ACCESS_OPTIONS,
  GUIDED_INJURY_SEVERITY_OPTIONS,
  getOptionLabel,
  getOptionLabels,
  isValidRecordFormat,
  KEY_GOAL_OPTIONS,
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
  buildGuidedInjurySummary,
  coerceGuidedInjuryEditState,
  EMPTY_GUIDED_INJURY,
  getInjuryMismatchContextKey,
  hasGuidedInjuryContent,
  hasGuidedInjuryDescriptorWithoutArea,
  hasMeaningfulInjuryMismatch,
  hydrateGuidedInjuryStates,
  type GuidedInjuryState,
} from "@/lib/guided-injury";
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
  shouldHideField,
  shouldDisableField,
  shouldDeEmphasizeField,
  getFieldHelperText,
  type DaysOutContext,
} from "@/lib/days-out-policy";
import type { PlanRequest } from "@/lib/types";

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
const INJURY_TREND_OPTIONS = [
  { label: "Stable", value: "stable" },
  { label: "Improving", value: "improving" },
  { label: "Getting worse", value: "worsening" },
];

type DraftMetadata = {
  current_step?: number;
  guided_injury?: Partial<GuidedInjuryState> | null;
  guided_injuries?: Array<Partial<GuidedInjuryState> | null> | null;
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
}: {
  currentStep: number;
  isOpen: boolean;
  onToggle: () => void;
  onStepSelect: (step: number) => void;
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
}: {
  label: string;
  options: IntakeOption[];
  selectedValues: string[];
  onToggle: (value: string) => void;
  disableAdditionalSelections?: boolean;
  disableAll?: boolean;
}) {
  return (
    <div className="field">
      <span className="checkbox-group-label">{label}</span>
      <div className="checkbox-grid">
        {options.map((option) => {
          const checked = selectedValues.includes(option.value);
          const disabled = disableAll || (disableAdditionalSelections && !checked);
          return (
            <label
              key={option.value}
              className={`checkbox-card ${checked ? "checkbox-card-checked" : ""} ${disabled ? "checkbox-card-disabled" : ""}`.trim()}
              aria-disabled={disabled}
            >
              <input type="checkbox" checked={checked} disabled={disabled} onChange={() => onToggle(option.value)} />
              <span className="checkbox-card-copy">
                <span className="checkbox-card-title">{option.label}</span>
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

function getReviewStepBlockingIssue(
  nextForm: PlanRequest,
  options: {
    injuryMismatchExists: boolean;
    injuryOverwriteAcknowledged: boolean;
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
  if (options.injuryMismatchExists && !options.injuryOverwriteAcknowledged) {
    return { message: "Acknowledge the injury note overwrite warning before continuing to review.", step: 3 };
  }
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
  const [isMobileProgressOpen, setIsMobileProgressOpen] = useState(true);
  const [form, setForm] = useState<PlanRequest>(emptyPlanRequest());
  const [guidedInjuries, setGuidedInjuries] = useState<GuidedInjuryState[]>([]);
  const [activeGuidedInjuryIndex, setActiveGuidedInjuryIndex] = useState<number | null>(null);
  const [noRestrictions, setNoRestrictions] = useState(true);
  const [bodyMapSide, setBodyMapSide] = useState<BodyMapSide>("front");
  const [hydrated, setHydrated] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const [originalInjuriesText, setOriginalInjuriesText] = useState<string>("");
  const [injuryOverwriteAcknowledged, setInjuryOverwriteAcknowledged] = useState(false);
  const [acknowledgedHardSparringWarningKey, setAcknowledgedHardSparringWarningKey] = useState<string | null>(null);
  const injuryMismatchContextKeyRef = useRef("");
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

    setOriginalInjuriesText(nextForm.injuries || "");
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

  const injuryMismatchContextKey = getInjuryMismatchContextKey(originalInjuriesText, form.injuries || "");
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
    if (!hydrated) {
      injuryMismatchContextKeyRef.current = injuryMismatchContextKey;
      return;
    }

    if (injuryMismatchContextKeyRef.current !== injuryMismatchContextKey) {
      setInjuryOverwriteAcknowledged(false);
    }

    injuryMismatchContextKeyRef.current = injuryMismatchContextKey;
  }, [hydrated, injuryMismatchContextKey]);

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
    const nextGuidedInjuries = [...guidedInjuries];
    nextGuidedInjuries[index] = coerceGuidedInjuryEditState({
      ...(nextGuidedInjuries[index] ?? EMPTY_GUIDED_INJURY),
      [key]: value,
    });
    syncGuidedInjuryFields(nextGuidedInjuries, false);
  }

  function handleEditGuidedInjury(index: number) {
    setActiveGuidedInjuryIndex(index);
  }

  function handleNoRestrictionsChange(checked: boolean) {
    if (!checked) {
      const nextGuidedInjuries = guidedInjuries.length ? guidedInjuries : [{ ...EMPTY_GUIDED_INJURY }];
      syncGuidedInjuryFields(nextGuidedInjuries, false);
      setActiveGuidedInjuryIndex(nextGuidedInjuries.length - 1);
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
    key: "training_availability" | "equipment_access" | "key_goals" | "weak_areas" | "hard_sparring_days" | "technical_skill_days",
    value: string,
  ) {
    setForm((current) => {
      const currentValues = key === "equipment_access"
        ? retainKnownOptionValues(current[key], EQUIPMENT_ACCESS_OPTIONS)
        : current[key];
      const alreadySelected = currentValues.includes(value);
      const isPerformanceFocusField = key === "key_goals" || key === "weak_areas";
      const performanceFocusCap = isPerformanceFocusField
        ? getPerformanceFocusCap(current.fight_date, { timeZone: current.athlete.athlete_timezone })
        : null;
      const totalSelectedPerformanceFocus = current.key_goals.length + current.weak_areas.length;

      if (isPerformanceFocusField && !alreadySelected && performanceFocusCap && totalSelectedPerformanceFocus >= performanceFocusCap.maxSelections) {
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
      nextForm.technical_skill_days,
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
    if (currentStep === 3 && hasMeaningfulInjuryMismatch(originalInjuriesText, nextForm.injuries || "") && !injuryOverwriteAcknowledged) {
      setError("Acknowledge the injury note overwrite warning before continuing.");
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
    if (hasMeaningfulInjuryMismatch(originalInjuriesText, nextForm.injuries || "") && !injuryOverwriteAcknowledged) {
      setError("Acknowledge the injury note overwrite warning in the Restrictions step before generating.");
      return false;
    }
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
      try {
        await persistDraft(nextStep);
      } catch {
        // Draft persistence is best-effort; navigation has already advanced.
      }
    });
  }

  function handleBack() {
    setCurrentStep((step) => Math.max(step - 1, 0));
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
        injuryMismatchExists,
        injuryOverwriteAcknowledged,
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

  const technicalStyleLabel = getOptionLabel(TECHNICAL_STYLE_OPTIONS, form.athlete.technical_style[0] ?? "") || "Not provided";
  const tacticalStyleLabel = getOptionLabel(TACTICAL_STYLE_OPTIONS, form.athlete.tactical_style[0] ?? "") || "Not provided";
  const statusLabel = getOptionLabel(PROFESSIONAL_STATUS_OPTIONS, form.athlete.professional_status ?? "") || "Not provided";
  const stanceLabel = getOptionLabel(STANCE_OPTIONS, form.athlete.stance ?? "") || "Not provided";
  const parsedRounds = parseRoundsFormat(form.rounds_format);
  const injuryMismatchExists = Boolean(injuryMismatchContextKey);
  const injuryGateLocked = injuryMismatchExists && !injuryOverwriteAcknowledged;
  const availabilityConsistency = getAvailabilityConsistency(
    form.training_availability,
    form.weekly_training_frequency,
  );
  const selectedTrainingAvailabilityLabels = getOptionLabels(TRAINING_AVAILABILITY_OPTIONS, form.training_availability);
  const selectedEquipmentAccessLabels = getOptionLabels(EQUIPMENT_ACCESS_OPTIONS, form.equipment_access);
  const selectedHardSparringLabels = getOptionLabels(TRAINING_AVAILABILITY_OPTIONS, form.hard_sparring_days);
  const selectedTechnicalSkillLabels = getOptionLabels(TRAINING_AVAILABILITY_OPTIONS, form.technical_skill_days);
  const selectedGoalLabels = getOptionLabels(KEY_GOAL_OPTIONS, form.key_goals);
  const selectedWeakAreaLabels = getOptionLabels(WEAK_AREA_OPTIONS, form.weak_areas);
  const performanceFocusCap = getPerformanceFocusCap(form.fight_date, {
    timeZone: form.athlete.athlete_timezone,
  });
  const selectedPerformanceFocusCount = performanceFocusValidation.totalSelections;
  const performanceFocusCapValue = performanceFocusCap?.maxSelections ?? null;
  const performanceFocusCapReached = performanceFocusCapValue !== null && selectedPerformanceFocusCount >= performanceFocusCapValue;
  const performanceFocusCapExceeded = performanceFocusValidation.isOverCap;
  const remainingPerformanceFocusSelections = performanceFocusCapValue === null
    ? null
    : Math.max(performanceFocusCapValue - selectedPerformanceFocusCount, 0);
  const performanceFocusWindowLabel = performanceFocusCap?.windowLabel.toLowerCase() ?? "this camp window";
  const performanceFocusReason = performanceFocusCap?.reason ?? "";
  const selectedTrainingAvailability = formatJoinedLabels(selectedTrainingAvailabilityLabels, "No availability selected");
  const selectedEquipmentAccess = formatJoinedLabels(selectedEquipmentAccessLabels, "No equipment selected");
  const selectedHardSparring = formatJoinedLabels(selectedHardSparringLabels, "No fixed hard sparring days");
  const selectedTechnicalSkillDays = formatJoinedLabels(selectedTechnicalSkillLabels, "No fixed technical-only days");
  const selectedGoals = formatJoinedLabels(selectedGoalLabels, "No goals selected");
  const selectedWeakAreas = formatJoinedLabels(selectedWeakAreaLabels, "No weak areas selected");
  const performanceFocusCapTitle = performanceFocusCapValue === null
    ? "Set a fight date to calculate your focus cap"
    : `${selectedPerformanceFocusCount} of ${performanceFocusCapValue} focus picks used`;
  const performanceFocusCapDetail = performanceFocusCapValue === null
    ? "Goals and weak areas share a cap once the fight date is set so the plan can match the camp window."
    : performanceFocusCapExceeded
      ? `Goals and weak areas share this ${performanceFocusCapValue}-pick cap for ${performanceFocusWindowLabel}. ${performanceFocusReason} You are ${selectedPerformanceFocusCount - performanceFocusCapValue} over the current cap, so unselect to get back within it.`
      : performanceFocusCapReached
        ? `Goals and weak areas share this ${performanceFocusCapValue}-pick cap for ${performanceFocusWindowLabel}. ${performanceFocusReason} Cap reached. Unselect one to change your focus.`
        : `Goals and weak areas share this ${performanceFocusCapValue}-pick cap for ${performanceFocusWindowLabel}. ${performanceFocusReason} You can add ${remainingPerformanceFocusSelections} more.`;
  const weightCutStatus = formatWeightCutStatus(form.athlete.weight_kg, form.athlete.target_weight_kg);
  const equipmentLimitations = formatEquipmentLimitations(form.equipment_access);
  const sparringConsistency = getSparringConsistency(
    form.training_availability,
    form.hard_sparring_days,
    form.technical_skill_days,
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
  const plannerRestrictionPreview = formatRestrictionSummary(form.injuries);
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
    { label: "Technical / lighter skill days", value: selectedTechnicalSkillDays },
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
    { label: "Key goals", value: selectedGoals },
    { label: "Weak areas", value: selectedWeakAreas },
    ...(mindsetChallengesText ? [{ label: "Mental / confidence issue", value: mindsetChallengesText }] : []),
    ...(notesText ? [{ label: "Anything else we should know?", value: notesText }] : []),
    ...(!hasExtraPerformanceNotes ? [{ label: "Extra context", value: "No extra context provided." }] : []),
  ];

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
        />

        <div className="athlete-motion-slot athlete-motion-status onboarding-progress-desktop">
          <OnboardingProgressStrip currentStep={currentStep} />
          <StepPills currentStep={currentStep} onStepSelect={handleStepSelect} />
        </div>

        {daysOutCtx.uiHints.fight_proximity_banner ? (
          <div className="fight-proximity-banner" role="status">
            {daysOutCtx.uiHints.fight_proximity_banner}
          </div>
        ) : null}

        {currentStep === 0 ? (
          <div className="step-layout onboarding-step-layout">
            <div className="step-main athlete-motion-slot athlete-motion-main onboarding-step-main">
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">Identity</p>
                  <h2 className="form-section-title">Core athlete details</h2>
                </div>
                <div className="form-grid">
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
                    <input id="age" type="number" min="0" value={form.athlete.age ?? ""} onChange={(event) => updateAthlete("age", numberOrNull(event.target.value))} />
                  </div>
                  <div className="field">
                    <label htmlFor="weightKg">Weight (kg)</label>
                    <input id="weightKg" type="number" min="0" step="0.1" value={form.athlete.weight_kg ?? ""} onChange={(event) => updateAthlete("weight_kg", numberOrNull(event.target.value))} />
                    <p className="muted">Use current walking-around weight.</p>
                  </div>
                  <div className="field">
                    <label htmlFor="targetWeightKg">Target weight (kg)</label>
                    <input id="targetWeightKg" type="number" min="0" step="0.1" value={form.athlete.target_weight_kg ?? ""} onChange={(event) => updateAthlete("target_weight_kg", numberOrNull(event.target.value))} />
                    <p className="muted">Use realistic fight-week target, not an ideal someday number.</p>
                  </div>
                  <div className="field">
                    <label htmlFor="heightCm">Height (cm)</label>
                    <input id="heightCm" type="number" min="0" step="1" value={form.athlete.height_cm ?? ""} onChange={(event) => updateAthlete("height_cm", integerOrNull(event.target.value))} />
                  </div>
                  <div className="field">
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
                <div className="form-grid">
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
          <div className="step-layout onboarding-step-layout">
            <div className="step-main athlete-motion-slot athlete-motion-main onboarding-step-main">
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">Fight context</p>
                  <h2 className="form-section-title">Camp timing and load</h2>
                </div>
                <div className="form-grid">
                  <div className="field">
                    <label htmlFor="fightDate">Fight date</label>
                    <input id="fightDate" type="date" value={form.fight_date} onChange={(event) => updateField("fight_date", event.target.value)} />
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
                  {shouldHideField(daysOutCtx, "weekly_training_frequency") ? (
                  <div className="field">
                    <p className="muted" style={{ opacity: 0.5 }}>Weekly session count is not used for planning at this stage.</p>
                  </div>
                  ) : (
                  <div className="field" style={shouldDeEmphasizeField(daysOutCtx, "weekly_training_frequency") ? { opacity: 0.55 } : undefined}>
                    <label htmlFor="sessionsPerWeek">Planned sessions per week</label>
                    <input
                      id="sessionsPerWeek"
                      type="number"
                      min="1"
                      max="6"
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
                        "Count the total training sessions the week should carry. Hard sparring days and technical / lighter skill days are labels inside that weekly total, not extra sessions on top."}
                    </p>
                  </div>
                  )}
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
                <div className={`support-panel ${hardSparringWarningLocked ? "support-panel-alert" : ""}`.trim()}>
                  <p className="kicker">High-contact warning</p>
                  <p className={hardSparringWarningLocked ? "error-text" : "muted"}>{hardSparringWarning.message}</p>
                  <label className={`checkbox-card ${hardSparringWarningAcknowledged ? "checkbox-card-checked" : ""}`.trim()}>
                    <input
                      type="checkbox"
                      checked={hardSparringWarningAcknowledged}
                      onChange={(event) => {
                        setAcknowledgedHardSparringWarningKey(
                          event.target.checked ? hardSparringWarning.acknowledgementContextKey : null,
                        );
                      }}
                    />
                    <span className="checkbox-card-copy">
                      <span className="checkbox-card-title">I understand this hard sparring load needs deliberate recovery planning.</span>
                    </span>
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
                  <h2 className="form-section-title">Sparring and skill day tags</h2>
                </div>
                <p className="muted">
                  These selections do not add extra sessions. They just show which available days are hard-contact days versus
                  lighter technical work inside the same weekly total.
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
                {shouldHideField(daysOutCtx, "technical_skill_days") ? (
                  <div className="field">
                    <p className="muted" style={{ opacity: 0.5 }}>Technical / skill day selection is not used for planning at this stage.</p>
                  </div>
                ) : (
                <>
                <CheckboxGroup
                  label="Technical / lighter skill days"
                  options={TRAINING_AVAILABILITY_OPTIONS}
                  selectedValues={form.technical_skill_days}
                  onToggle={(value) => toggleFieldValue("technical_skill_days", value)}
                  disableAll={shouldDisableField(daysOutCtx, "technical_skill_days")}
                />
                <div className="field">
                  <p className="muted">
                    {getFieldHelperText(daysOutCtx, "technical_skill_days") ||
                      "Use this for lighter drilling, pads, partner technical work, or skill-focused days that should stay cleaner than hard sparring days."}
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
                  <li>Technical / lighter skill days: {selectedTechnicalSkillDays}</li>
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
          <div className="step-layout onboarding-step-layout">
            <div className="step-main athlete-motion-slot athlete-motion-main onboarding-step-main">
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">Restrictions</p>
                  <h2 className="form-section-title">Injuries or restrictions</h2>
                </div>
                {injuryMismatchExists ? (
                  <div className={`support-panel ${injuryGateLocked ? "support-panel-alert" : ""}`.trim()}>
                    <p className="kicker">Warning: existing injury note will be overwritten</p>
                    <p className={injuryGateLocked ? "error-text" : "muted"}>
                      The structured fields produce a summary that differs from the existing injury note. Saving or generating will replace the original wording with the structured summary. Review the difference below before continuing.
                    </p>
                    <div className="injury-overwrite-diff">
                      <div className="injury-overwrite-diff-block">
                        <p className="kicker">Original note</p>
                        <p className="muted">{originalInjuriesText}</p>
                      </div>
                      <div className="injury-overwrite-diff-block">
                        <p className="kicker">Generated summary</p>
                        <p className="muted">{form.injuries?.trim() || "No structured summary generated."}</p>
                      </div>
                    </div>
                    <label className={`checkbox-card ${injuryOverwriteAcknowledged ? "checkbox-card-checked" : ""}`.trim()}>
                      <input
                        type="checkbox"
                        checked={injuryOverwriteAcknowledged}
                        onChange={(event) => setInjuryOverwriteAcknowledged(event.target.checked)}
                      />
                      <span className="checkbox-card-copy">
                        <span className="checkbox-card-title">I understand the original note may be simplified or replaced. Continue with the structured summary.</span>
                      </span>
                    </label>
                  </div>
                ) : null}
                <label className={`checkbox-card ${noRestrictions ? "checkbox-card-checked" : ""}`.trim()}>
                  <input
                    type="checkbox"
                    checked={noRestrictions}
                    onChange={(event) => handleNoRestrictionsChange(event.target.checked)}
                  />
                  <span className="checkbox-card-copy">
                    <span className="checkbox-card-title">No current injuries or restrictions</span>
                    <span className="checkbox-card-description">Leave this checked when the athlete has nothing the planner needs to work around.</span>
                  </span>
                </label>
                {!noRestrictions ? (
                  <>
                    <div className="injury-body-map-layout">
                      <div className="injury-body-map-col">
                        <BodyMap
                          side={bodyMapSide}
                          usedAreas={guidedInjuries.map((injury) => injury.area)}
                          onZoneSelect={handleBodyMapZoneSelect}
                          onSideChange={setBodyMapSide}
                        />
                      </div>
                      <div className="injury-cards-col">
                        <div className="injury-card-stack">
                          {guidedInjuries.map((injury, index) => {
                            const isActive = activeGuidedInjuryIndex === index;
                            const injuryLabel = injury.area.trim() || `Injury ${index + 1}`;
                            const injurySummary = buildGuidedInjurySummary(injury) || "No injury details added yet.";

                            return (
                              <section key={`guided-injury-${index}`} className={`injury-card ${isActive ? "injury-card-active" : ""}`.trim()}>
                                <div
                                  className="injury-card-header injury-card-header-interactive"
                                  onClick={() => (isActive ? setActiveGuidedInjuryIndex(null) : handleEditGuidedInjury(index))}
                                  onKeyDown={(event) => {
                                    if (event.key === "Enter" || event.key === " ") {
                                      event.preventDefault();
                                      if (isActive) {
                                        setActiveGuidedInjuryIndex(null);
                                      } else {
                                        handleEditGuidedInjury(index);
                                      }
                                    }
                                  }}
                                  role="button"
                                  tabIndex={0}
                                  aria-expanded={isActive}
                                >
                                  <div className="injury-card-num">{String(index + 1).padStart(2, "0")}</div>
                                  <div className="injury-card-copy">
                                    <h3 className="injury-card-title">{injuryLabel}</h3>
                                    {!isActive ? <p className="injury-card-summary">{injurySummary}</p> : null}
                                  </div>
                                  <div className="injury-card-badges">
                                    {injury.severity ? (
                                      <span className={`injury-severity-badge injury-severity-badge-${injury.severity}`}>
                                        {injury.severity.charAt(0).toUpperCase() + injury.severity.slice(1)}
                                      </span>
                                    ) : null}
                                    {injury.trend ? (
                                      <span className={`injury-trend-badge injury-trend-badge-${injury.trend}`}>
                                        {injury.trend === "improving" ? "\u2197" : injury.trend === "worsening" ? "\u2198" : "\u2192"}{" "}
                                        {injury.trend.charAt(0).toUpperCase() + injury.trend.slice(1)}
                                      </span>
                                    ) : null}
                                  </div>
                                  <button
                                    type="button"
                                    className="injury-card-remove-btn"
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      handleRemoveGuidedInjury(index);
                                    }}
                                    aria-label={`Remove ${injuryLabel}`}
                                  >
                                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                                      <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                                    </svg>
                                  </button>
                                </div>
                                {isActive ? (
                                  <div className="injury-card-form">
                                    <div className="field">
                                      <label htmlFor={`injuryArea-${index}`}>Injury or pain area</label>
                                      <input
                                        id={`injuryArea-${index}`}
                                        value={injury.area ?? ""}
                                        onChange={(event) => updateGuidedInjury(index, "area", event.target.value)}
                                        placeholder="Left shoulder"
                                      />
                                    </div>
                                    <div className="form-grid">
                                      <div className="field">
                                        <label>Current severity</label>
                                        <div className="injury-severity-chips">
                                          {GUIDED_INJURY_SEVERITY_OPTIONS.map((option) => (
                                            <button
                                              key={option.value}
                                              type="button"
                                              className={`injury-severity-chip ${injury.severity === option.value ? `injury-severity-chip-${option.value}` : ""}`.trim()}
                                              onClick={() => updateGuidedInjury(index, "severity", injury.severity === option.value ? "" : option.value)}
                                            >
                                              {option.label}
                                            </button>
                                          ))}
                                        </div>
                                      </div>
                                      <div className="field">
                                        <label>Current trend</label>
                                        <div className="injury-trend-chips">
                                          {INJURY_TREND_OPTIONS.map((option) => {
                                            const arrow = option.value === "improving" ? "\u2197" : option.value === "worsening" ? "\u2198" : "\u2192";

                                            return (
                                              <button
                                                key={option.value}
                                                type="button"
                                                className={`injury-trend-chip ${injury.trend === option.value ? `injury-trend-chip-${option.value}` : ""}`.trim()}
                                                onClick={() => updateGuidedInjury(index, "trend", injury.trend === option.value ? "" : option.value)}
                                              >
                                                {arrow} {option.label}
                                              </button>
                                            );
                                          })}
                                        </div>
                                      </div>
                                    </div>
                                    <div className="field">
                                      <label htmlFor={`injuryAvoid-${index}`}>Movements to avoid (optional)</label>
                                      <input
                                        id={`injuryAvoid-${index}`}
                                        value={injury.avoid ?? ""}
                                        onChange={(event) => updateGuidedInjury(index, "avoid", event.target.value)}
                                        placeholder="Heavy overhead pressing, hard sprinting, deep knee flexion"
                                      />
                                    </div>
                                    <div className="field">
                                      <label htmlFor={`injuryNotes-${index}`}>Extra details</label>
                                      <textarea
                                        id={`injuryNotes-${index}`}
                                        value={injury.notes ?? ""}
                                        onChange={(event) => updateGuidedInjury(index, "notes", event.target.value)}
                                        placeholder="What happened, what irritates it, and anything the planner should work around for this issue"
                                      />
                                    </div>
                                  </div>
                                ) : null}
                              </section>
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
                  </>
                ) : (
                  <div className="support-panel support-panel-preview support-panel-success compact-gap">
                    <p className="kicker">Restrictions step complete</p>
                    <p className="muted">No restrictions are being sent to the planner. You can continue now or uncheck this later if something needs to be worked around.</p>
                  </div>
                )}
                <div className="support-panel support-panel-preview compact-gap">
                  <p className="kicker">Planner note preview</p>
                  <p className="muted">
                    {plannerRestrictionPreview}
                  </p>
                </div>
              </article>
            </div>

            <aside className="step-aside athlete-motion-slot athlete-motion-rail onboarding-step-aside">
              <div className="support-panel">
                <p className="kicker">Safety</p>
                <p className="muted">Give each issue its own card so the planner can see every restriction clearly. Use Add injury for second or third issues, and leave the toggle on when there is nothing to protect around.</p>
              </div>
            </aside>
          </div>
        ) : null}

        {currentStep === 4 ? (
          <div className="step-layout onboarding-step-layout">
            <div className="step-main athlete-motion-slot athlete-motion-main onboarding-step-main">
              <article className={`support-panel ${performanceFocusCapExceeded ? "support-panel-alert" : ""}`.trim()}>
                <div className="form-section-header">
                  <p className="kicker">Focus cap</p>
                  <h2 className="form-section-title">{performanceFocusCapTitle}</h2>
                </div>
                <p className="muted">{performanceFocusCapDetail}</p>
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
                />
                {getFieldHelperText(daysOutCtx, "key_goals") ? (
                  <p className="muted">{getFieldHelperText(daysOutCtx, "key_goals")}</p>
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
                />
                {getFieldHelperText(daysOutCtx, "weak_areas") ? (
                  <p className="muted">{getFieldHelperText(daysOutCtx, "weak_areas")}</p>
                ) : null}
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
            </div>

            <aside className="step-aside athlete-motion-slot athlete-motion-rail onboarding-step-aside">
              <div className="status-card">
                <p className="status-label">Ready to generate</p>
                <h2 className="plan-summary-title">Final pre-check</h2>
                <p className="muted">Review the saved inputs, then generate.</p>
                <ul className="summary-list">
                  <li>Technical Style must be selected.</li>
                  <li>Fight date must be set.</li>
                  <li>Training Availability needs at least one selected option.</li>
                  <li>Planned sessions per week must be at least 1.</li>
                  {availabilityConsistency.hardError ? <li>{availabilityConsistency.hardError}</li> : null}
                  {sparringConsistency.hardError ? <li>{sparringConsistency.hardError}</li> : null}
                  {hardSparringWarning.message ? (
                    <li>
                      {hardSparringWarning.message}
                      {hardSparringWarningAcknowledged ? " Acknowledged in Training." : " Return to Training to acknowledge it."}
                    </li>
                  ) : null}
                </ul>
              </div>
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

        <div className="form-actions athlete-motion-slot athlete-motion-rail">
          <button type="button" className="ghost-button" onClick={handleSaveDraft} disabled={isPending}>
            {isPending ? "Saving..." : "Save draft"}
          </button>
          {currentStep > 0 ? (
            <button type="button" className="ghost-button" onClick={handleBack}>
              Back
            </button>
          ) : null}
          {currentStep < steps.length - 1 ? (
            <button type="button" className="cta" onClick={handleNext} disabled={isPending}>
              Continue
            </button>
          ) : (
            <>
              <button type="button" className="cta" onClick={handleGenerate} disabled={isPending}>
                Generate plan
              </button>
              <Link href="/plans" className="ghost-button">
                View plan history
              </Link>
            </>
          )}
        </div>
      </section>
    </RequireAuth>
  );
}
