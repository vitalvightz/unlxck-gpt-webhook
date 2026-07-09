"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, useTransition } from "react";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { CustomSelect } from "@/components/custom-select";
import { WhyTooltip } from "@/components/why-tooltip";
import { saveOnboardingDraft } from "@/lib/api";
import { writePendingGenerationPayload } from "@/lib/generation-pending-payload";
import { markGenerationIntent } from "@/lib/generation-intent";
import { hydratePlanRequest, mergeSavedOnboardingDraft } from "@/lib/onboarding";
import {
  EQUIPMENT_ACCESS_OPTIONS,
  KEY_GOAL_OPTIONS,
  TACTICAL_STYLE_OPTIONS,
  TECHNICAL_STYLE_OPTIONS,
  TRAINING_AVAILABILITY_OPTIONS,
  WEAK_AREA_OPTIONS,
  toggleListValue,
  type IntakeOption,
} from "@/lib/intake-options";
import { FOCUS_CAP_DISABLED_REASON, validatePerformanceFocusSelections } from "@/lib/performance-focus-cap";
import { HARD_SPARRING_DAY_CAP } from "@/lib/training-schedule";
import {
  buildDaysOutContext,
  computeDaysUntilFight,
  filterAvailablePerformanceFocusValues,
  getPerformanceFocusOptionAvailability,
  HARD_SPARRING_STRENGTH_REMOVAL_MESSAGE,
} from "@/lib/days-out-policy";
import {
  buildRoundsFormat,
  parseRoundsFormat,
  ROUND_COUNT_OPTIONS,
  ROUND_DURATION_OPTIONS,
} from "@/lib/rounds-format";
import {
  QUICK_BUILD_KEY_GOAL_CAP,
  QUICK_BUILD_WEAK_AREA_CAP,
  emptyQuickBuildInput,
  planRequestToQuickBuildInput,
  quickBuildToPlanRequest,
  validateQuickBuildInput,
  type QuickBuildInput,
  type QuickBuildValidationErrors,
} from "@/lib/quick-build";
import { ATHLETE_FULL_NAME_MAX } from "@/lib/input-limits";
import {
  EQUIPMENT_PRESETS,
  TRAINING_PRESETS,
  deriveSetupSource,
  getAvailableFocusPresets,
  matchesEquipmentPreset,
  matchesFocusPreset,
  matchesTrainingPreset,
  resolveFocusPresetSelections,
  type EquipmentPreset,
  type EquipmentPresetKey,
  type FocusPreset,
  type FocusPresetKey,
  type TrainingPreset,
  type TrainingPresetKey,
} from "@/lib/recommended-setup";

const WEEKLY_FREQUENCY_OPTIONS: IntakeOption[] = Array.from({ length: 6 }, (_, index) => ({
  label: String(index + 1),
  value: String(index + 1),
}));

type QuickBuildStarter = {
  key: string;
  label: string;
  description: string;
  trainingPreset: TrainingPresetKey;
  equipmentPreset: EquipmentPresetKey;
  focusPreset: FocusPresetKey;
};

const QUICK_BUILD_STARTERS: QuickBuildStarter[] = [
  {
    key: "balanced",
    label: "Balanced camp",
    description: "4 days, basic gym, gas tank",
    trainingPreset: "four_days",
    equipmentPreset: "basic_gym",
    focusPreset: "gas_tank",
  },
  {
    key: "power",
    label: "Power build",
    description: "5 days, full gym, power",
    trainingPreset: "five_days",
    equipmentPreset: "full_gym",
    focusPreset: "explosive_power",
  },
  {
    key: "speed",
    label: "Speed camp",
    description: "4 days, basic gym, speed",
    trainingPreset: "four_days",
    equipmentPreset: "basic_gym",
    focusPreset: "speed_footwork",
  },
  {
    key: "cut_support",
    label: "Cut support",
    description: "5 days, basic gym, weight cut",
    trainingPreset: "five_days",
    equipmentPreset: "basic_gym",
    focusPreset: "weight_cut_support",
  },
  {
    key: "home_control",
    label: "Home control",
    description: "3 days, home kit, mobility",
    trainingPreset: "three_days",
    equipmentPreset: "home",
    focusPreset: "mobility_control",
  },
];

type QuickBuildGuideStep = {
  key: string;
  label: string;
  detail: string;
  complete: boolean;
};

type ChipMultiSelectProps = {
  label: string;
  options: IntakeOption[];
  selectedValues: string[];
  onToggle: (value: string) => void;
  capDisabledReason?: string;
  disableAdditionalSelections?: boolean;
  disabledValues?: string[];
  disabledValueReason?: string;
  getOptionDisabledReason?: (option: IntakeOption, checked: boolean) => string | null;
};

function ChipMultiSelect({
  label,
  options,
  selectedValues,
  onToggle,
  capDisabledReason,
  disableAdditionalSelections = false,
  disabledValues,
  disabledValueReason,
  getOptionDisabledReason,
}: ChipMultiSelectProps) {
  const disabledValueSet = disabledValues && disabledValues.length > 0 ? new Set(disabledValues) : null;
  return (
    <div className="field">
      <span className="checkbox-group-label">{label}</span>
      <div className="checkbox-grid">
        {options.map((option) => {
          const checked = selectedValues.includes(option.value);
          const optionDisabledReason = getOptionDisabledReason?.(option, checked) ?? null;
          const valueDisabled = !checked && (Boolean(optionDisabledReason) || disabledValueSet?.has(option.value) === true);
          const capDisabled = !valueDisabled && disableAdditionalSelections && !checked;
          const disabled = valueDisabled || capDisabled;
          const reason = valueDisabled ? optionDisabledReason ?? disabledValueReason : capDisabled ? capDisabledReason : undefined;
          return (
            <label
              key={option.value}
              className={`checkbox-card ${checked ? "checkbox-card-checked" : ""} ${disabled ? "checkbox-card-disabled" : ""}`.trim()}
              aria-disabled={disabled}
              title={disabled ? reason : undefined}
            >
              <input
                type="checkbox"
                checked={checked}
                disabled={disabled}
                onChange={() => onToggle(option.value)}
              />
              <span className="checkbox-card-copy">
                <span className="checkbox-card-title">{option.label}</span>
              </span>
              {disabled && reason ? (
                <WhyTooltip
                  title="Unavailable"
                  body={reason}
                  triggerLabel="?"
                  ariaLabel={`Why ${option.label} is unavailable`}
                />
              ) : null}
            </label>
          );
        })}
      </div>
    </div>
  );
}

function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return (
    <p className="quick-build-field-error" role="alert">
      {message}
    </p>
  );
}

function QuickBuildGuide({ steps }: { steps: QuickBuildGuideStep[] }) {
  const completedCount = steps.filter((step) => step.complete).length;
  const totalCount = steps.length;
  const nextStep = steps.find((step) => !step.complete);
  const progressPct = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  return (
    <section className="quick-build-guide" aria-label="Quick Build progress">
      <div className="quick-build-guide-header">
        <div>
          <p className="kicker">Fast path</p>
          <h2 className="quick-build-guide-title">Quick Build readiness</h2>
        </div>
        <span className={completedCount === totalCount ? "badge status-badge-success" : "badge status-badge-neutral"}>
          {completedCount}/{totalCount} ready
        </span>
      </div>
      <div className="overview-progress-track quick-build-guide-track" role="presentation" aria-hidden="true">
        <span className="overview-progress-fill quick-build-guide-fill" style={{ width: `${progressPct}%` }} />
      </div>
      <div className="quick-build-guide-steps">
        {steps.map((step, index) => {
          const isCurrent = nextStep?.key === step.key;
          return (
            <div
              key={step.key}
              className={`quick-build-guide-step ${step.complete ? "quick-build-guide-step-complete" : ""} ${isCurrent ? "quick-build-guide-step-current" : ""}`.trim()}
            >
              <span className="quick-build-guide-step-index">{String(index + 1).padStart(2, "0")}</span>
              <span className="quick-build-guide-step-copy">
                <span className="quick-build-guide-step-label">{step.label}</span>
                <span className="quick-build-guide-step-detail">{step.complete ? "Ready" : step.detail}</span>
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

type LabelledPreset = {
  key: string;
  label: string;
  description: string;
};

function presetToOption(preset: LabelledPreset): IntakeOption {
  return {
    label: `${preset.label} - ${preset.description}`,
    value: preset.key,
  };
}

function PresetSelect({
  id,
  label,
  placeholder,
  options,
  activeKey,
  onSelect,
}: {
  id: string;
  label: string;
  placeholder: string;
  options: IntakeOption[];
  activeKey: string | null;
  onSelect: (key: string) => void;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <CustomSelect
        id={id}
        value={options.some((o) => o.value === activeKey) ? (activeKey ?? "") : ""}
        options={options}
        placeholder={placeholder}
        includeEmptyOption
        onChange={onSelect}
      />
    </div>
  );
}

function QuickBuildFormInner() {
  const router = useRouter();
  const { me, session, replaceMe } = useAppSession();
  const [input, setInput] = useState<QuickBuildInput>(() =>
    me
      ? planRequestToQuickBuildInput(hydratePlanRequest(me))
      : emptyQuickBuildInput(""),
  );
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [showErrors, setShowErrors] = useState(false);
  const [isPending, startTransition] = useTransition();

  const errors: QuickBuildValidationErrors = useMemo(() => validateQuickBuildInput(input), [input]);
  const parsedRounds = parseRoundsFormat(input.rounds_format);
  const focusValidation = useMemo(
    () => (!input.no_scheduled_fight && input.fight_date
      ? validatePerformanceFocusSelections(input.fight_date, { keyGoals: input.key_goals, weakAreas: input.weak_areas }, { timeZone: typeof Intl !== "undefined" ? Intl.DateTimeFormat().resolvedOptions().timeZone : null })
      : null),
    [input.no_scheduled_fight, input.fight_date, input.key_goals, input.weak_areas],
  );
  const daysUntilFight = useMemo(
    () => (input.no_scheduled_fight ? null : computeDaysUntilFight(input.fight_date)),
    [input.fight_date, input.no_scheduled_fight],
  );
  const hasHardSparring = input.hard_sparring_days.length > 0;
  const daysOutCtx = useMemo(
    () => buildDaysOutContext(daysUntilFight, { hasHardSparring }),
    [daysUntilFight, hasHardSparring],
  );
  const sharedFocusCap = focusValidation?.cap?.maxSelections ?? null;
  const sharedFocusCount = input.key_goals.length + input.weak_areas.length;
  const sharedFocusCapReached = sharedFocusCap !== null && sharedFocusCount >= sharedFocusCap;
  const focusPresetLimits = useMemo(
    () => ({
      goalLimit: QUICK_BUILD_KEY_GOAL_CAP,
      weakAreaLimit: QUICK_BUILD_WEAK_AREA_CAP,
      sharedLimit: sharedFocusCap,
      daysOutCtx,
    }),
    [daysOutCtx, sharedFocusCap],
  );
  const unavailableGoalValues = useMemo(
    () => KEY_GOAL_OPTIONS
      .filter((option) => !getPerformanceFocusOptionAvailability(daysOutCtx, "key_goals", option.value).available)
      .map((option) => option.value),
    [daysOutCtx],
  );
  const unavailableWeakAreaValues = useMemo(
    () => WEAK_AREA_OPTIONS
      .filter((option) => !getPerformanceFocusOptionAvailability(daysOutCtx, "weak_areas", option.value).available)
      .map((option) => option.value),
    [daysOutCtx],
  );

  const activeEquipmentPreset = useMemo(
    () => matchesEquipmentPreset(input.equipment_access),
    [input.equipment_access],
  );
  const activeTrainingPreset = useMemo(
    () => matchesTrainingPreset(input.training_availability, input.weekly_training_frequency),
    [input.training_availability, input.weekly_training_frequency],
  );
  const activeFocusPreset = useMemo(
    () => matchesFocusPreset(input.key_goals, input.weak_areas, focusPresetLimits),
    [focusPresetLimits, input.key_goals, input.weak_areas],
  );
  const availableFocusPresets = useMemo(
    () => getAvailableFocusPresets({
      fightDate: input.fight_date,
      noScheduledFight: input.no_scheduled_fight,
      limits: focusPresetLimits,
    }),
    [focusPresetLimits, input.fight_date, input.no_scheduled_fight],
  );
  const maxWeeklySessions = input.training_availability.length;
  const sessionsSelectDisabled = maxWeeklySessions === 0;
  const weeklyFrequencyOptions = useMemo(
    () => (maxWeeklySessions > 0 ? WEEKLY_FREQUENCY_OPTIONS.slice(0, maxWeeklySessions) : []),
    [maxWeeklySessions],
  );
  const activeStarterPreset = useMemo(
    () =>
      QUICK_BUILD_STARTERS.find(
        (starter) =>
          activeTrainingPreset === starter.trainingPreset &&
          activeEquipmentPreset === starter.equipmentPreset &&
          activeFocusPreset === starter.focusPreset,
      )?.key ?? null,
    [activeEquipmentPreset, activeFocusPreset, activeTrainingPreset],
  );
  const availableStarters = useMemo(() => {
    const availableFocusKeys = new Set(
      availableFocusPresets
        .filter((entry) => !entry.disabledReason)
        .map((entry) => entry.preset.key),
    );
    return QUICK_BUILD_STARTERS.filter((starter) => availableFocusKeys.has(starter.focusPreset));
  }, [availableFocusPresets]);

  const trainingPresetOptions: IntakeOption[] = useMemo(
    () => TRAINING_PRESETS.map((preset) => presetToOption(preset)),
    [],
  );

  const equipmentPresetOptions: IntakeOption[] = useMemo(
    () => EQUIPMENT_PRESETS.map((preset) => presetToOption(preset)),
    [],
  );

  const focusPresetOptions: IntakeOption[] = useMemo(
    () =>
      availableFocusPresets
        .filter((entry) => !entry.disabledReason)
        .map((entry) => presetToOption(entry.preset)),
    [availableFocusPresets],
  );
  const hasValidationErrors = Object.keys(errors).length > 0;
  const quickBuildGuideSteps: QuickBuildGuideStep[] = useMemo(() => {
    const profileComplete = Boolean(input.full_name.trim()) && input.technical_style.length > 0 && !errors.full_name && !errors.technical_style;
    const fightComplete = Boolean(input.no_scheduled_fight || input.fight_date) && !errors.fight_date && !errors.rounds_format;
    const scheduleComplete =
      input.training_availability.length > 0 &&
      input.equipment_access.length > 0 &&
      !errors.training_availability &&
      !errors.weekly_training_frequency &&
      !errors.hard_sparring_days &&
      !errors.equipment_access;
    const focusComplete = input.key_goals.length > 0 && !errors.key_goals && !errors.weak_areas && !errors.focus_cap;
    const generateComplete = Object.keys(errors).length === 0;

    return [
      { key: "profile", label: "Profile", detail: "Name and style", complete: profileComplete },
      { key: "fight", label: "Fight", detail: "Date or open camp", complete: fightComplete },
      { key: "schedule", label: "Schedule", detail: "Days, sessions, kit", complete: scheduleComplete },
      { key: "focus", label: "Focus", detail: "Goals selected", complete: focusComplete },
      { key: "generate", label: "Generate", detail: "Ready to build", complete: generateComplete },
    ];
  }, [input, errors]);
  const readyToGenerate = !hasValidationErrors;

  useEffect(() => {
    setInput((current) => {
      const nextKeyGoals = filterAvailablePerformanceFocusValues(daysOutCtx, "key_goals", current.key_goals);
      const nextWeakAreas = filterAvailablePerformanceFocusValues(daysOutCtx, "weak_areas", current.weak_areas);
      if (nextKeyGoals.length === current.key_goals.length && nextWeakAreas.length === current.weak_areas.length) {
        return current;
      }
      const removedStrengthForHardSparring =
        daysOutCtx.hasHardSparring &&
        daysOutCtx.daysOut !== null &&
        daysOutCtx.daysOut <= 20 &&
        (current.key_goals.includes("strength") || current.weak_areas.includes("strength"));
      setMessage(
        removedStrengthForHardSparring
          ? HARD_SPARRING_STRENGTH_REMOVAL_MESSAGE
          : "Some picks were removed because they are not available this close to fight day.",
      );
      return {
        ...current,
        key_goals: nextKeyGoals,
        weak_areas: nextWeakAreas,
      };
    });
  }, [daysOutCtx]);

  function patch<K extends keyof QuickBuildInput>(key: K, value: QuickBuildInput[K]) {
    if (submitError) {
      setSubmitError(null);
    }
    if (message) {
      setMessage(null);
    }
    setInput((current) => ({ ...current, [key]: value }));
  }

  function toggleField(key: keyof Pick<QuickBuildInput, "technical_style" | "tactical_style" | "training_availability" | "hard_sparring_days" | "equipment_access" | "key_goals" | "weak_areas">, value: string) {
    if (submitError) {
      setSubmitError(null);
    }
    if (message) {
      setMessage(null);
    }
    setInput((current) => {
      const nextValues = toggleListValue(current[key], value);
      if (key === "training_availability") {
        const isRemoving = current.training_availability.includes(value) && !nextValues.includes(value);
        // Sessions per week follows the day count (one session per training day)
        // until the athlete overrides it, so most athletes never touch the field.
        const trackedFrequency = (dayCount: number) =>
          Math.max(1, Math.min(dayCount, WEEKLY_FREQUENCY_OPTIONS.length));
        const currentFrequency = current.weekly_training_frequency ?? 1;
        const wasTrackingDays =
          current.training_availability.length === 0 ||
          currentFrequency === trackedFrequency(current.training_availability.length);
        const nextFrequency = wasTrackingDays
          ? trackedFrequency(nextValues.length)
          : Math.min(currentFrequency, Math.max(nextValues.length, 1));
        return {
          ...current,
          training_availability: nextValues,
          hard_sparring_days: isRemoving
            ? current.hard_sparring_days.filter((day) => day !== value)
            : current.hard_sparring_days,
          weekly_training_frequency: nextFrequency,
        };
      }
      return { ...current, [key]: nextValues };
    });
  }

  function togglePerformanceFocusField(key: "key_goals" | "weak_areas", value: string) {
    if (submitError) {
      setSubmitError(null);
    }
    setInput((current) => {
      const isSelected = current[key].includes(value);
      if (!isSelected) {
        const availability = getPerformanceFocusOptionAvailability(daysOutCtx, key, value);
        if (!availability.available) {
          return current;
        }
      }

      const nextValues = toggleListValue(current[key], value);
      const next = { ...current, [key]: nextValues };
      return {
        ...next,
        key_goals: key === "key_goals" ? filterAvailablePerformanceFocusValues(daysOutCtx, "key_goals", next.key_goals) : next.key_goals,
        weak_areas: key === "weak_areas" ? filterAvailablePerformanceFocusValues(daysOutCtx, "weak_areas", next.weak_areas) : next.weak_areas,
      };
    });
  }

  function confirmReplace(currentHasValues: boolean, message: string): boolean {
    if (!currentHasValues) return true;
    if (typeof window === "undefined") return true;
    return window.confirm(message);
  }

  function applyStarterPreset(starter: QuickBuildStarter) {
    if (message) {
      setMessage(null);
    }
    const trainingPreset = TRAINING_PRESETS.find((entry) => entry.key === starter.trainingPreset);
    const equipmentPreset = EQUIPMENT_PRESETS.find((entry) => entry.key === starter.equipmentPreset);
    const focusEntry = availableFocusPresets.find(
      (entry) => entry.preset.key === starter.focusPreset && !entry.disabledReason,
    );
    if (!trainingPreset || !equipmentPreset || !focusEntry) {
      return;
    }
    // Only prompt when the user has manual selections AND no starter is currently
    // active. Switching from one active starter to another applies immediately.
    const hasManualChoice =
      activeStarterPreset === null &&
      (
        input.training_availability.length > 0 ||
        input.hard_sparring_days.length > 0 ||
        input.equipment_access.length > 0 ||
        input.key_goals.length > 0 ||
        input.weak_areas.length > 0
      );
    if (!confirmReplace(hasManualChoice, "Replace your current starter setup selections?")) {
      return;
    }
    setSubmitError(null);
    const focusSelections = resolveFocusPresetSelections(focusEntry.preset, focusPresetLimits);
    setInput((currentInput) => ({
      ...currentInput,
      training_availability: [...trainingPreset.training_availability],
      weekly_training_frequency: trainingPreset.weekly_training_frequency,
      hard_sparring_days: currentInput.hard_sparring_days.filter((day) =>
        trainingPreset.training_availability.includes(day),
      ),
      equipment_access: [...equipmentPreset.equipment_access],
      key_goals: focusSelections.key_goals,
      weak_areas: focusSelections.weak_areas,
    }));
  }

  function clearStarterPreset() {
    if (message) {
      setMessage(null);
    }
    setSubmitError(null);
    setInput((current) => ({
      ...current,
      training_availability: [],
      weekly_training_frequency: 4,
      hard_sparring_days: [],
      equipment_access: [],
      key_goals: [],
      weak_areas: [],
    }));
  }

  function applyEquipmentPreset(preset: EquipmentPreset) {
    if (message) {
      setMessage(null);
    }
    setSubmitError(null);
    patch("equipment_access", [...preset.equipment_access]);
  }

  function clearEquipmentPreset() {
    if (message) {
      setMessage(null);
    }
    setSubmitError(null);
    patch("equipment_access", []);
  }

  function applyTrainingPreset(preset: TrainingPreset) {
    if (message) {
      setMessage(null);
    }
    setSubmitError(null);
    setInput((currentInput) => ({
      ...currentInput,
      training_availability: [...preset.training_availability],
      weekly_training_frequency: preset.weekly_training_frequency,
      hard_sparring_days: currentInput.hard_sparring_days.filter((day) => preset.training_availability.includes(day)),
    }));
  }

  function clearTrainingPreset() {
    if (message) {
      setMessage(null);
    }
    setSubmitError(null);
    setInput((currentInput) => ({
      ...currentInput,
      training_availability: [],
      hard_sparring_days: [],
    }));
  }

  function applyFocusPreset(preset: FocusPreset) {
    if (message) {
      setMessage(null);
    }
    setSubmitError(null);
    const focusSelections = resolveFocusPresetSelections(preset, focusPresetLimits);
    setInput((currentInput) => ({
      ...currentInput,
      key_goals: focusSelections.key_goals,
      weak_areas: focusSelections.weak_areas,
    }));
  }

  function clearFocusPreset() {
    if (message) {
      setMessage(null);
    }
    setSubmitError(null);
    setInput((currentInput) => ({
      ...currentInput,
      key_goals: [],
      weak_areas: [],
    }));
  }

  function handleStarterCardClick(starter: QuickBuildStarter) {
    if (activeStarterPreset === starter.key) {
      clearStarterPreset();
      return;
    }
    applyStarterPreset(starter);
  }

  function handleTrainingPresetSelect(key: string) {
    if (!key) {
      clearTrainingPreset();
      return;
    }
    const preset = TRAINING_PRESETS.find((entry) => entry.key === key);
    if (preset) applyTrainingPreset(preset);
  }

  function handleEquipmentPresetSelect(key: string) {
    if (!key) {
      clearEquipmentPreset();
      return;
    }
    const preset = EQUIPMENT_PRESETS.find((entry) => entry.key === key);
    if (preset) applyEquipmentPreset(preset);
  }

  function handleFocusPresetSelect(key: string) {
    if (!key) {
      clearFocusPreset();
      return;
    }
    const entry = availableFocusPresets.find((candidate) => candidate.preset.key === key);
    if (entry && !entry.disabledReason) applyFocusPreset(entry.preset);
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitError(null);
    const currentErrors = validateQuickBuildInput(input);
    const currentFocusValidation = (!input.no_scheduled_fight && input.fight_date)
      ? validatePerformanceFocusSelections(input.fight_date, { keyGoals: input.key_goals, weakAreas: input.weak_areas }, { timeZone: typeof Intl !== "undefined" ? Intl.DateTimeFormat().resolvedOptions().timeZone : null })
      : null;
    if (currentFocusValidation?.isOverCap) {
      currentErrors.focus_cap = currentFocusValidation.errorMessage ?? "Adjust goals and weak areas before generating.";
    }
    if (Object.keys(currentErrors).length > 0) {
      setShowErrors(true);
      const errorCount = Object.keys(currentErrors).length;
      setSubmitError(`Fix ${errorCount} highlighted ${errorCount === 1 ? "field" : "fields"} before generating.`);
      return;
    }
    if (!session?.access_token) {
      setSubmitError("Session expired. Sign in again.");
      return;
    }

    startTransition(async () => {
      try {
        const planRequest = quickBuildToPlanRequest(input);
        const equipmentPresetMatch = matchesEquipmentPreset(planRequest.equipment_access);
        const trainingPresetMatch = matchesTrainingPreset(
          planRequest.training_availability,
          planRequest.weekly_training_frequency ?? 0,
        );
        const focusPresetMatch = matchesFocusPreset(planRequest.key_goals, planRequest.weak_areas, focusPresetLimits);
        const draft = {
          ...planRequest,
          current_step: 0,
          plan_source: "quick_build" as const,
          setup_source: deriveSetupSource([
            equipmentPresetMatch,
            trainingPresetMatch,
            focusPresetMatch,
          ]),
          equipment_preset: equipmentPresetMatch,
          training_preset: trainingPresetMatch,
          focus_preset: focusPresetMatch,
        };
        await saveOnboardingDraft(session.access_token, {
          full_name: planRequest.athlete.full_name,
          technical_style: planRequest.athlete.technical_style,
          tactical_style: planRequest.athlete.tactical_style,
          stance: planRequest.athlete.stance ?? "",
          professional_status: planRequest.athlete.professional_status ?? "",
          record: planRequest.athlete.record ?? "",
          athlete_timezone: planRequest.athlete.athlete_timezone ?? "",
          onboarding_draft: draft,
        });

        const nextMe = mergeSavedOnboardingDraft(me, draft, planRequest.athlete);
        if (nextMe) {
          replaceMe(nextMe);
        }
        if (!writePendingGenerationPayload(planRequest, "quick_build")) {
          setSubmitError("Unable to prepare the generation payload. Reload and try again.");
          return;
        }
        markGenerationIntent();
        router.push("/generate");
      } catch (err) {
        const message = err instanceof Error ? err.message : "";
        if (message.toLowerCase().includes("session") || message.includes("401")) {
          setSubmitError("Session expired. Sign in again.");
        } else if (message.includes("Unable to reach the server") || message.includes("502") || message.includes("503") || message.includes("504")) {
          setSubmitError("Connection issue. Try again in a minute.");
        } else {
          setSubmitError(message || "Unable to save plan. Please try again.");
        }
      }
    });
  }

  const visibleError = (key: keyof QuickBuildValidationErrors): string | undefined =>
    showErrors ? errors[key] : undefined;
  const submitErrorId = "quick-build-submit-feedback";

  return (
    <form onSubmit={handleSubmit} className="onboarding-form quick-build-form">
      <section className="hero-panel">
        <p className="eyebrow">Quick Build</p>
        <h1 className="hero-title">Generate a plan in about two minutes.</h1>
        <p className="muted">
          Quick Build uses safe defaults for fatigue, sparring intensity, and goal prioritization. Use Advanced Intake for full
          control - you can also refine this plan afterwards.
        </p>
      </section>

      <QuickBuildGuide steps={quickBuildGuideSteps} />

      <section className="quick-build-starters" aria-label="Starter setups">
        <div className="quick-build-starters-copy">
          <span className="checkbox-group-label">One-tap starters</span>
          <p className="muted">
            Tap a starter to fill your schedule, equipment, and focus in one go. Adjust anything below, or tap again to
            clear.
          </p>
        </div>
        <div className="quick-build-starter-grid">
          {availableStarters.map((starter) => {
            const active = activeStarterPreset === starter.key;
            return (
              <button
                key={starter.key}
                type="button"
                className={`quick-build-starter-card ${active ? "quick-build-starter-card-active" : ""}`.trim()}
                aria-pressed={active}
                onClick={() => handleStarterCardClick(starter)}
              >
                <span className="quick-build-starter-card-label">{starter.label}</span>
                <span className="quick-build-starter-card-detail">{starter.description}</span>
              </button>
            );
          })}
        </div>
      </section>

      <article className="step-card">
        <div className="form-section-header">
          <p className="kicker">Profile</p>
          <h2 className="form-section-title">Athlete</h2>
        </div>
        <div className="field">
          <label htmlFor="qb-full-name">Full name</label>
          <input
            id="qb-full-name"
            type="text"
            value={input.full_name}
            onChange={(event) => patch("full_name", event.target.value)}
            autoComplete="name"
            maxLength={ATHLETE_FULL_NAME_MAX}
            required
          />
          <FieldError message={visibleError("full_name")} />
        </div>
        <div className="field">
          <label htmlFor="qb-technical-style">Technical style</label>
          <CustomSelect
            id="qb-technical-style"
            value={input.technical_style[0] ?? ""}
            options={TECHNICAL_STYLE_OPTIONS}
            placeholder="Select technical style"
            includeEmptyOption
            onChange={(value) => patch("technical_style", value ? [value] : [])}
          />
        </div>
        <FieldError message={visibleError("technical_style")} />
        <div className="field">
          <label htmlFor="qb-tactical-style">Tactical style (optional)</label>
          <CustomSelect
            id="qb-tactical-style"
            value={input.tactical_style[0] ?? ""}
            options={TACTICAL_STYLE_OPTIONS}
            placeholder="Select tactical style"
            includeEmptyOption
            onChange={(value) => patch("tactical_style", value ? [value] : [])}
          />
        </div>
        <FieldError message={visibleError("tactical_style")} />
      </article>

      <article className="step-card">
        <div className="form-section-header">
          <p className="kicker">Fight context</p>
          <h2 className="form-section-title">When are you fighting?</h2>
        </div>
        <div className="field">
          <label className="checkbox-card" style={{ maxWidth: "100%" }}>
            <input
              type="checkbox"
              checked={input.no_scheduled_fight}
              onChange={(event) => {
                setSubmitError(null);
                setInput((current) => ({
                  ...current,
                  no_scheduled_fight: event.target.checked,
                  fight_date: event.target.checked ? "" : current.fight_date,
                }));
              }}
            />
            <span className="checkbox-card-copy">
              <span className="checkbox-card-title">No scheduled fight</span>
              <span className="checkbox-card-tag">Open camp - General prep</span>
            </span>
          </label>
        </div>
        {!input.no_scheduled_fight ? (
          <div className="field">
            <label htmlFor="qb-fight-date">Fight date</label>
            <input
              id="qb-fight-date"
              type="date"
              value={input.fight_date}
              onChange={(event) => patch("fight_date", event.target.value)}
            />
            <FieldError message={visibleError("fight_date")} />
          </div>
        ) : null}

        <div className="form-grid">
          <div className="field">
            <label htmlFor="qb-round-count">Rounds</label>
            <CustomSelect
              id="qb-round-count"
              value={parsedRounds.roundCount}
              options={ROUND_COUNT_OPTIONS}
              placeholder="Rounds"
              onChange={(value) =>
                patch("rounds_format", buildRoundsFormat(value, parsedRounds.roundDuration || "3"))
              }
            />
          </div>
          <div className="field">
            <label htmlFor="qb-round-duration">Round length</label>
            <CustomSelect
              id="qb-round-duration"
              value={parsedRounds.roundDuration}
              options={ROUND_DURATION_OPTIONS}
              placeholder="Duration"
              onChange={(value) =>
                patch("rounds_format", buildRoundsFormat(parsedRounds.roundCount || "3", value))
              }
            />
          </div>
        </div>
        <FieldError message={visibleError("rounds_format")} />
      </article>

      <article className="step-card">
        <div className="form-section-header">
          <p className="kicker">Training</p>
          <h2 className="form-section-title">Weekly schedule</h2>
        </div>
        <PresetSelect
          id="qb-training-preset"
          label="Recommended training (optional)"
          placeholder="Optional training preset"
          options={trainingPresetOptions}
          activeKey={activeTrainingPreset}
          onSelect={handleTrainingPresetSelect}
        />
        <ChipMultiSelect
          label="Days you can train"
          options={TRAINING_AVAILABILITY_OPTIONS}
          selectedValues={input.training_availability}
          onToggle={(value) => toggleField("training_availability", value)}
        />
        <ChipMultiSelect
          label="Hard sparring days"
          options={TRAINING_AVAILABILITY_OPTIONS}
          selectedValues={input.hard_sparring_days}
          onToggle={(value) => toggleField("hard_sparring_days", value)}
          disabledValues={TRAINING_AVAILABILITY_OPTIONS
            .filter((option) => !input.training_availability.includes(option.value))
            .map((option) => option.value)}
          disabledValueReason="Add as a training day first"
          disableAdditionalSelections={input.hard_sparring_days.length >= HARD_SPARRING_DAY_CAP}
          capDisabledReason={`Hard sparring cap (${HARD_SPARRING_DAY_CAP}) reached`}
        />
        <p className="muted">Leave empty if you don&apos;t hard spar. Used to place S&amp;C around sparring.</p>
        <FieldError message={visibleError("hard_sparring_days")} />
        <div className="field">
          <label htmlFor="qb-weekly-frequency">Sessions per week</label>
          <CustomSelect
            id="qb-weekly-frequency"
            value={String(input.weekly_training_frequency)}
            options={weeklyFrequencyOptions}
            placeholder={sessionsSelectDisabled ? "Choose training days first" : "Sessions"}
            disabled={sessionsSelectDisabled}
            onChange={(value) => patch("weekly_training_frequency", Number(value) || 1)}
          />
          <p className="muted">Matches your training days automatically. Lower it if some days should stay light.</p>
          <FieldError message={visibleError("weekly_training_frequency")} />
          <FieldError message={visibleError("training_availability")} />
        </div>
        <PresetSelect
          id="qb-equipment-preset"
          label="Recommended equipment (optional)"
          placeholder="Optional equipment preset"
          options={equipmentPresetOptions}
          activeKey={activeEquipmentPreset}
          onSelect={handleEquipmentPresetSelect}
        />
        <ChipMultiSelect
          label="Equipment access"
          options={EQUIPMENT_ACCESS_OPTIONS}
          selectedValues={input.equipment_access}
          onToggle={(value) => toggleField("equipment_access", value)}
        />
        <FieldError message={visibleError("equipment_access")} />
      </article>

      <article className="step-card">
        <div className="form-section-header">
          <p className="kicker">Performance</p>
          <h2 className="form-section-title">Goals and weak areas</h2>
        </div>
        <PresetSelect
          id="qb-focus-preset"
          label="Recommended focus (optional)"
          placeholder="Optional focus preset"
          options={focusPresetOptions}
          activeKey={activeFocusPreset}
          onSelect={handleFocusPresetSelect}
        />
        <ChipMultiSelect
          label={sharedFocusCap !== null ? `Key goals (shared cap: ${sharedFocusCap})` : `Key goals (pick up to ${QUICK_BUILD_KEY_GOAL_CAP})`}
          options={KEY_GOAL_OPTIONS}
          selectedValues={input.key_goals}
          onToggle={(value) => togglePerformanceFocusField("key_goals", value)}
          disableAdditionalSelections={input.key_goals.length >= QUICK_BUILD_KEY_GOAL_CAP || sharedFocusCapReached}
          capDisabledReason={sharedFocusCapReached ? FOCUS_CAP_DISABLED_REASON : `Limit ${QUICK_BUILD_KEY_GOAL_CAP}`}
          disabledValues={unavailableGoalValues}
          disabledValueReason="Not available for this fight window"
          getOptionDisabledReason={(option, checked) => {
            if (checked) return null;
            const availability = getPerformanceFocusOptionAvailability(daysOutCtx, "key_goals", option.value);
            return availability.available ? null : availability.reason ?? "Not available for this fight window";
          }}
        />
        <FieldError message={visibleError("key_goals")} />
        <ChipMultiSelect
          label={sharedFocusCap !== null ? `Weak areas (shared cap: ${sharedFocusCap})` : `Weak areas (optional, up to ${QUICK_BUILD_WEAK_AREA_CAP})`}
          options={WEAK_AREA_OPTIONS}
          selectedValues={input.weak_areas}
          onToggle={(value) => togglePerformanceFocusField("weak_areas", value)}
          disableAdditionalSelections={input.weak_areas.length >= QUICK_BUILD_WEAK_AREA_CAP || sharedFocusCapReached}
          capDisabledReason={sharedFocusCapReached ? FOCUS_CAP_DISABLED_REASON : `Limit ${QUICK_BUILD_WEAK_AREA_CAP}`}
          disabledValues={unavailableWeakAreaValues}
          disabledValueReason="Not available for this fight window"
          getOptionDisabledReason={(option, checked) => {
            if (checked) return null;
            const availability = getPerformanceFocusOptionAvailability(daysOutCtx, "weak_areas", option.value);
            return availability.available ? null : availability.reason ?? "Not available for this fight window";
          }}
        />
        <FieldError message={visibleError("weak_areas")} />
        <FieldError message={visibleError("focus_cap")} />
      </article>

      <article className="step-card">
        <div className="form-section-header">
          <p className="kicker">Restrictions (optional)</p>
          <h2 className="form-section-title">Injuries or limitations</h2>
        </div>
        <div className="field">
          <label htmlFor="qb-injuries">Anything the planner should avoid (injuries, pain, or limitations)</label>
          <textarea
            id="qb-injuries"
            value={input.injuries}
            onChange={(event) => patch("injuries", event.target.value)}
            placeholder="Example: Left knee sprain. Avoid jumping and hard pivots for 2 weeks."
          />
          <p className="muted">Be specific. Include body area, injury type, and what to avoid.</p>
        </div>
      </article>

      <div className="form-actions quick-build-action-bar">
        <div className="quick-build-action-copy">
          <p className="quick-build-action-title">
            {readyToGenerate ? "Ready to generate." : "Quick Build is almost ready."}
          </p>
          <p className="muted">Refine fatigue, sparring days, and detailed weaknesses later from the plan page.</p>
        </div>
        {message ? (
          <div className="quick-build-action-feedback" role="status" aria-live="polite">
            <span className="quick-build-action-feedback-label">Notice</span>
            <span>{message}</span>
          </div>
        ) : null}
        {submitError ? (
          <div id={submitErrorId} className="quick-build-action-feedback" role="alert" aria-live="assertive">
            <span className="quick-build-action-feedback-label">Check</span>
            <span>{submitError}</span>
          </div>
        ) : null}
        <div className="plan-summary-actions quick-build-action-buttons">
          <button type="submit" className="cta" disabled={isPending} aria-describedby={submitError ? submitErrorId : undefined}>
            {isPending ? "Saving..." : "Generate Plan"}
          </button>
          <Link href="/onboarding" className="ghost-button">
            Use Advanced Intake instead
          </Link>
        </div>
      </div>
    </form>
  );
}

export function QuickBuildForm() {
  return (
    <RequireAuth>
      <QuickBuildFormInner />
    </RequireAuth>
  );
}
