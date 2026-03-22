"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, useTransition } from "react";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { CustomSelect } from "@/components/custom-select";
import { updateMe } from "@/lib/api";
import {
  detectDeviceLocale,
  detectDeviceTimeZone,
  EQUIPMENT_ACCESS_OPTIONS,
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
import { emptyPlanRequest, hydratePlanRequest } from "@/lib/onboarding";
import type { PlanRequest } from "@/lib/types";

const steps = ["Profile", "Fight Context", "Training", "Restrictions", "Performance", "Review"] as const;
const ROUND_COUNT_OPTIONS = Array.from({ length: 12 }, (_, index) => ({
  label: String(index + 1),
  value: String(index + 1),
}));
const ROUND_DURATION_OPTIONS = [
  { label: "1 minute", value: "1" },
  { label: "2 minutes", value: "2" },
  { label: "3 minutes", value: "3" },
  { label: "5 minutes", value: "5" },
];
const FATIGUE_LEVEL_OPTIONS = [
  { label: "Low", value: "low" },
  { label: "Moderate", value: "moderate" },
  { label: "High", value: "high" },
];
const INJURY_SEVERITY_OPTIONS = [
  { label: "Low", value: "low" },
  { label: "Moderate", value: "moderate" },
  { label: "High", value: "high" },
];
const INJURY_TREND_OPTIONS = [
  { label: "Stable", value: "stable" },
  { label: "Improving", value: "improving" },
  { label: "Getting worse", value: "worsening" },
];

type GuidedInjuryState = {
  id: string;
  area: string;
  severity: string;
  trend: string;
  avoid: string;
  notes: string;
};

type GuidedInjuryDraftState = Omit<GuidedInjuryState, "id">;

type AvailabilityConsistency = {
  hardError: string | null;
  softWarning: string | null;
};

type SparringConsistency = {
  hardError: string | null;
  softWarning: string | null;
};

type DraftMetadata = {
  current_step?: number;
  guided_injury?: Partial<GuidedInjuryDraftState> | null;
  guided_injuries?: Partial<GuidedInjuryState>[] | null;
  active_guided_injury_id?: string | null;
};

function createGuidedInjury(area = ""): GuidedInjuryState {
  return {
    id: `injury-${Math.random().toString(36).slice(2, 10)}`,
    area: area.trim(),
    severity: "",
    trend: "",
    avoid: "",
    notes: "",
  };
}


function numberOrNull(value: string): number | null {
  if (!value.trim()) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
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

function formatJoinedLabels(values: string[], emptyLabel: string): string {
  return values.length ? values.join(", ") : emptyLabel;
}

function parseRoundsFormat(value: string | null | undefined): { roundCount: string; roundDuration: string } {
  const raw = (value ?? "").trim();
  const match = raw.match(/(\d+)\s*x\s*(\d+)/i) ?? raw.match(/(\d+)\s*[xX]\s*(\d+)/);
  if (!match) {
    return { roundCount: "", roundDuration: "" };
  }
  return {
    roundCount: match[1] ?? "",
    roundDuration: match[2] ?? "",
  };
}

function buildRoundsFormat(roundCount: string, roundDuration: string): string {
  if (!roundCount || !roundDuration) {
    return "";
  }
  return `${roundCount} x ${roundDuration}`;
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

function getAvailabilityConsistency(
  trainingAvailability: string[],
  weeklyTrainingFrequency: number | null | undefined,
): AvailabilityConsistency {
  const availableDays = trainingAvailability.length;
  const sessionsPerWeek = weeklyTrainingFrequency ?? 0;
  const unusedDays = Math.max(availableDays - sessionsPerWeek, 0);

  if (!availableDays || !sessionsPerWeek) {
    return { hardError: null, softWarning: null };
  }

  if (sessionsPerWeek > availableDays) {
    return {
      hardError: `You selected ${availableDays} available day${availableDays === 1 ? "" : "s"} but asked for ${sessionsPerWeek} sessions per week.`,
      softWarning: null,
    };
  }

  if (unusedDays >= 3 && sessionsPerWeek <= 3) {
    return {
      hardError: null,
      softWarning: `You have ${availableDays} days available but only ${sessionsPerWeek} planned sessions. That's fine if some days are optional.`,
    };
  }

  return { hardError: null, softWarning: null };
}

function getSparringConsistency(
  trainingAvailability: string[],
  hardSparringDays: string[],
  technicalSkillDays: string[],
): SparringConsistency {
  const available = new Set(trainingAvailability);
  const invalidHard = hardSparringDays.filter((day) => !available.has(day));
  if (invalidHard.length) {
    return {
      hardError: `Hard sparring days must also be selected as available days: ${invalidHard.join(", ")}.`,
      softWarning: null,
    };
  }

  const invalidTechnical = technicalSkillDays.filter((day) => !available.has(day));
  if (invalidTechnical.length) {
    return {
      hardError: `Technical skill days must also be selected as available days: ${invalidTechnical.join(", ")}.`,
      softWarning: null,
    };
  }

  const overlap = hardSparringDays.filter((day) => technicalSkillDays.includes(day));
  if (overlap.length) {
    return {
      hardError: `A day cannot be both hard sparring and technical-only: ${overlap.join(", ")}.`,
      softWarning: null,
    };
  }

  if (!hardSparringDays.length && technicalSkillDays.length) {
    return {
      hardError: null,
      softWarning: "Technical skill days are set, but hard sparring days are blank. That's fine if sparring is light or not fixed yet.",
    };
  }

  return { hardError: null, softWarning: null };
}

function normalizeGuidedInjuryState(value: Partial<GuidedInjuryState> | Partial<GuidedInjuryDraftState> | null | undefined): GuidedInjuryState {
  const id = value && "id" in value && typeof value.id === "string" && value.id.trim() ? value.id.trim() : createGuidedInjury().id;
  return {
    id,
    area: (value?.area ?? "").trim(),
    severity: (value?.severity ?? "").trim(),
    trend: (value?.trend ?? "").trim(),
    avoid: (value?.avoid ?? "").trim(),
    notes: (value?.notes ?? "").trim(),
  };
}

function parseGuidedInjuryState(value: string | null | undefined): GuidedInjuryState[] {
  const raw = (value ?? "").trim();
  if (!raw) {
    return [];
  }
  return [{
    ...createGuidedInjury(),
    notes: raw,
  }];
}

function buildGuidedInjurySummary(value: GuidedInjuryState): string {
  const details = normalizeGuidedInjuryState(value);
  const parts: string[] = [];

  if (details.area) {
    const descriptors = [details.severity, details.trend].filter(Boolean).join(", ");
    parts.push(descriptors ? `${details.area} (${descriptors})` : details.area);
  }
  if (details.avoid) {
    parts.push(`avoid ${details.avoid}`);
  }
  if (details.notes) {
    parts.push(details.notes);
  }

  return parts.join(". ").trim();
}

function buildGuidedInjuriesSummary(values: GuidedInjuryState[]): string {
  return values
    .map((value) => buildGuidedInjurySummary(value))
    .map((value) => value.trim())
    .filter(Boolean)
    .join("; ");
}

function parseAreaTokens(value: string): string[] {
  return value
    .split(/[;,\n]/)
    .map((entry) => entry.trim())
    .filter(Boolean);
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
        const isJumpable = index < steps.length - 1;
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

        if (!isJumpable) {
          return (
            <div key={label} className={`step-pill ${statusClass}`.trim()}>
              {pillContent}
            </div>
          );
        }

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

function CheckboxGroup({
  label,
  options,
  selectedValues,
  onToggle,
}: {
  label: string;
  options: IntakeOption[];
  selectedValues: string[];
  onToggle: (value: string) => void;
}) {
  return (
    <div className="field">
      <span className="checkbox-group-label">{label}</span>
      <div className="checkbox-grid">
        {options.map((option) => {
          const checked = selectedValues.includes(option.value);
          return (
            <label key={option.value} className={`checkbox-card ${checked ? "checkbox-card-checked" : ""}`.trim()}>
              <input type="checkbox" checked={checked} onChange={() => onToggle(option.value)} />
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

function syncDeviceFields(current: PlanRequest): PlanRequest {
  const detectedTimeZone = detectDeviceTimeZone();
  const detectedLocale = detectDeviceLocale();
  return {
    ...current,
    athlete: {
      ...current.athlete,
      athlete_timezone: detectedTimeZone || current.athlete.athlete_timezone || "",
      athlete_locale: detectedLocale || current.athlete.athlete_locale || "",
    },
  };
}

export function PlanIntakeForm() {
  const router = useRouter();
  const { me, refreshMe, session } = useAppSession();
  const [currentStep, setCurrentStep] = useState(0);
  const [form, setForm] = useState<PlanRequest>(emptyPlanRequest());
  const [guidedInjuries, setGuidedInjuries] = useState<GuidedInjuryState[]>([]);
  const [activeGuidedInjuryId, setActiveGuidedInjuryId] = useState<string | null>(null);
  const [injuryAreaInput, setInjuryAreaInput] = useState("");
  const [hydrated, setHydrated] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const recordHasError = !isValidRecordFormat(form.athlete.record ?? "");

  useEffect(() => {
    if (!me || hydrated) {
      return;
    }
    const nextForm = syncDeviceFields(hydratePlanRequest(me));
    const draft = (me.profile.onboarding_draft as DraftMetadata | null | undefined) ?? null;
    setForm(nextForm);
    const hydratedGuidedInjuries = draft?.guided_injuries?.length
      ? draft.guided_injuries.map((item) => normalizeGuidedInjuryState(item))
      : draft?.guided_injury
        ? [normalizeGuidedInjuryState(draft.guided_injury)]
        : parseGuidedInjuryState(nextForm.injuries);
    setGuidedInjuries(hydratedGuidedInjuries);
    setActiveGuidedInjuryId(
      draft?.active_guided_injury_id && hydratedGuidedInjuries.some((item) => item.id === draft.active_guided_injury_id)
        ? draft.active_guided_injury_id
        : hydratedGuidedInjuries[0]?.id ?? null,
    );
    const savedStep = Number(draft?.current_step ?? 0);
    setCurrentStep(Number.isFinite(savedStep) ? Math.min(Math.max(savedStep, 0), steps.length - 1) : 0);
    setHydrated(true);
  }, [hydrated, me]);

  useEffect(() => {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reducedMotion ? "instant" : "smooth" });
  }, [currentStep]);

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

  function addGuidedInjuryAreas(rawValue: string) {
    const nextAreas = parseAreaTokens(rawValue);
    if (!nextAreas.length) {
      return;
    }

    setGuidedInjuries((current) => {
      const existingAreas = new Set(current.map((item) => item.area.trim().toLowerCase()).filter(Boolean));
      const appended = nextAreas
        .filter((area) => !existingAreas.has(area.toLowerCase()))
        .map((area) => createGuidedInjury(area));
      const nextItems = [...current, ...appended];
      updateField("injuries", buildGuidedInjuriesSummary(nextItems));
      if (appended[0]) {
        setActiveGuidedInjuryId(appended[0].id);
      }
      return nextItems;
    });
    setInjuryAreaInput("");
  }

  function updateGuidedInjury<K extends keyof GuidedInjuryDraftState>(key: K, value: GuidedInjuryDraftState[K]) {
    setGuidedInjuries((current) => {
      const nextItems = current.map((item) =>
        item.id === activeGuidedInjuryId
          ? normalizeGuidedInjuryState({
              ...item,
              [key]: value,
            })
          : item,
      );
      updateField("injuries", buildGuidedInjuriesSummary(nextItems));
      return nextItems;
    });
  }

  function removeGuidedInjury(id: string) {
    setGuidedInjuries((current) => {
      const nextItems = current.filter((item) => item.id !== id);
      updateField("injuries", buildGuidedInjuriesSummary(nextItems));
      setActiveGuidedInjuryId((currentActiveId) => {
        if (currentActiveId !== id) {
          return currentActiveId;
        }
        return nextItems[0]?.id ?? null;
      });
      return nextItems;
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

      return {
        ...current,
        [key]: toggleListValue(currentValues, value),
      };
    });
  }

  function validateCurrentStep(nextForm: PlanRequest): boolean {
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
    if (currentStep === 2) {
      const scheduleCheck = getAvailabilityConsistency(
        nextForm.training_availability,
        nextForm.weekly_training_frequency,
      );
      if (scheduleCheck.hardError) {
        setError(`${scheduleCheck.hardError} Reduce sessions or add more available days.`);
        return false;
      }
      const sparringCheck = getSparringConsistency(
        nextForm.training_availability,
        nextForm.hard_sparring_days,
        nextForm.technical_skill_days,
      );
      if (sparringCheck.hardError) {
        setError(sparringCheck.hardError);
        return false;
      }
    }
    return true;
  }

  function validateForGeneration(nextForm: PlanRequest): boolean {
    if (!validateCurrentStep(nextForm)) {
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
      setError("Sessions per Week must be at least 1.");
      return false;
    }
    const parsedRounds = parseRoundsFormat(nextForm.rounds_format);
    if (!parsedRounds.roundCount || !parsedRounds.roundDuration) {
      setError("Choose both round count and round duration before generating your plan.");
      return false;
    }
    const scheduleCheck = getAvailabilityConsistency(
      nextForm.training_availability,
      nextForm.weekly_training_frequency,
    );
    if (scheduleCheck.hardError) {
      setError(`${scheduleCheck.hardError} Reduce sessions or add more available days.`);
      return false;
    }
    const sparringCheck = getSparringConsistency(
      nextForm.training_availability,
      nextForm.hard_sparring_days,
      nextForm.technical_skill_days,
    );
    if (sparringCheck.hardError) {
      setError(sparringCheck.hardError);
      return false;
    }
    return true;
  }

  async function persistDraft(step = currentStep) {
    if (!session?.access_token) {
      return;
    }
    const nextForm = syncDeviceFields(form);
    setForm(nextForm);
    await updateMe(session.access_token, {
      full_name: nextForm.athlete.full_name,
      technical_style: nextForm.athlete.technical_style,
      tactical_style: nextForm.athlete.tactical_style,
      stance: nextForm.athlete.stance,
      professional_status: nextForm.athlete.professional_status,
      record: nextForm.athlete.record,
      athlete_timezone: nextForm.athlete.athlete_timezone,
      athlete_locale: nextForm.athlete.athlete_locale,
      onboarding_draft: {
        ...nextForm,
        current_step: step,
        guided_injuries: guidedInjuries,
        active_guided_injury_id: activeGuidedInjuryId,
      },
    });
    await refreshMe();
  }

  function handleSaveDraft() {
    setMessage(null);
    setError(null);
    startTransition(async () => {
      const nextForm = syncDeviceFields(form);
      if (!validateCurrentStep(nextForm)) {
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
      const nextForm = syncDeviceFields(form);
      if (!validateCurrentStep(nextForm)) {
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
    if (targetStep < 0 || targetStep >= steps.length - 1) {
      return;
    }
    setMessage(null);
    setError(null);
    setCurrentStep(targetStep);

    if (!session?.access_token || !isValidRecordFormat(form.athlete.record ?? "")) {
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
      const nextForm = syncDeviceFields(form);
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
  const selectedTrainingAvailability = formatJoinedLabels(selectedTrainingAvailabilityLabels, "No availability selected");
  const selectedEquipmentAccess = formatJoinedLabels(selectedEquipmentAccessLabels, "No equipment selected");
  const selectedHardSparring = formatJoinedLabels(selectedHardSparringLabels, "No fixed hard sparring days");
  const selectedTechnicalSkillDays = formatJoinedLabels(selectedTechnicalSkillLabels, "No fixed technical-only days");
  const selectedGoals = formatJoinedLabels(selectedGoalLabels, "No goals selected");
  const selectedWeakAreas = formatJoinedLabels(selectedWeakAreaLabels, "No weak areas selected");
  const weightCutStatus = formatWeightCutStatus(form.athlete.weight_kg, form.athlete.target_weight_kg);
  const equipmentLimitations = formatEquipmentLimitations(form.equipment_access);
  const sparringConsistency = getSparringConsistency(
    form.training_availability,
    form.hard_sparring_days,
    form.technical_skill_days,
  );
  const activeGuidedInjury = useMemo(() => guidedInjuries.find((item) => item.id === activeGuidedInjuryId) ?? null, [guidedInjuries, activeGuidedInjuryId]);
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
  const profileReviewItems = [
    { label: "Name", value: formatValue(form.athlete.full_name) },
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
    { label: "Sessions per week", value: formatValue(form.weekly_training_frequency) },
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
    {
      label: "Session preference",
      value: hasTrainingPreference ? trainingPreferenceText : "No session preference provided.",
    },
  ];
  const constraintsReviewItems = [
    { label: "Injuries / pain areas", value: formatValue(form.injuries) },
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
      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="kicker">Athlete Onboarding</p>
            <h1>Build your camp profile.</h1>
            <p className="muted">Saved, resumable athlete intake.</p>
          </div>
          <div className="status-card">
            <p className="status-label">Current step</p>
            <h2 className="plan-summary-title">{steps[currentStep]}</h2>
            <p className="muted">Step {currentStep + 1} of {steps.length}. Draft keeps your selections and current step.</p>
          </div>
        </div>

        <StepPills currentStep={currentStep} onStepSelect={handleStepSelect} />

        {currentStep === 0 ? (
          <div className="step-layout">
            <div className="step-main">
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">Identity</p>
                  <h2 className="form-section-title">Core athlete details</h2>
                </div>
                <div className="form-grid">
                  <div className="field">
                    <label htmlFor="fullName">Full name</label>
                    <input id="fullName" value={form.athlete.full_name} onChange={(event) => updateAthlete("full_name", event.target.value)} required />
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
                    <input id="heightCm" type="number" min="0" value={form.athlete.height_cm ?? ""} onChange={(event) => updateAthlete("height_cm", numberOrNull(event.target.value))} />
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

            <aside className="step-aside">
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
          <div className="step-layout">
            <div className="step-main">
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
                  <div className="field">
                    <label htmlFor="sessionsPerWeek">Sessions per Week</label>
                    <input id="sessionsPerWeek" type="number" min="1" max="14" value={form.weekly_training_frequency ?? ""} onChange={(event) => updateField("weekly_training_frequency", numberOrNull(event.target.value))} />
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
                </div>
              </article>
            </div>

            <aside className="step-aside">
              <div className="support-panel">
                <div className="form-section-header">
                  <p className="kicker">Context snapshot</p>
                  <h2 className="form-section-title">Current camp setup</h2>
                </div>
                <ul className="summary-list">
                  <li>Fight date: {formatValue(form.fight_date)}</li>
                  <li>Rounds: {formatValue(form.rounds_format)}</li>
                  <li>Sessions per Week: {formatValue(form.weekly_training_frequency)}</li>
                  <li>Fatigue level: {formatValue(form.fatigue_level || "moderate")}</li>
                </ul>
              </div>
              <div className="support-panel">
                <p className="kicker">Guidance</p>
                <p className="muted">Fight date and training frequency shape the camp timeline.</p>
              </div>
            </aside>
          </div>
        ) : null}

        {currentStep === 2 ? (
          <div className="step-layout">
            <div className="step-main">
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">Schedule</p>
                  <h2 className="form-section-title">Training Availability</h2>
                </div>
                <CheckboxGroup
                  label="Training Availability"
                  options={TRAINING_AVAILABILITY_OPTIONS}
                  selectedValues={form.training_availability}
                  onToggle={(value) => toggleFieldValue("training_availability", value)}
                />
              </article>
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">Combat load</p>
                  <h2 className="form-section-title">Sparring and skill days</h2>
                </div>
                <CheckboxGroup
                  label="Hard Sparring Days"
                  options={TRAINING_AVAILABILITY_OPTIONS}
                  selectedValues={form.hard_sparring_days}
                  onToggle={(value) => toggleFieldValue("hard_sparring_days", value)}
                />
                <div className="field">
                  <p className="muted">Pick the days that usually carry the hardest live rounds or highest collision combat load.</p>
                </div>
                <CheckboxGroup
                  label="Technical / lighter skill days"
                  options={TRAINING_AVAILABILITY_OPTIONS}
                  selectedValues={form.technical_skill_days}
                  onToggle={(value) => toggleFieldValue("technical_skill_days", value)}
                />
                <div className="field">
                  <p className="muted">Use this for lighter technical boxing or skill-focused days that should stay cleaner than hard sparring days.</p>
                </div>
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
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">Training style</p>
                  <h2 className="form-section-title">Training Preference</h2>
                </div>
                  <div className="field">
                    <label htmlFor="trainingPreference">Session preference</label>
                    <textarea
                      id="trainingPreference"
                      value={form.training_preference ?? ""}
                      onChange={(event) => updateField("training_preference", event.target.value)}
                      placeholder="Example: shorter hard sessions, less circuit work, more technical warm-ups, avoid long grinders"
                    />
                    <p className="muted">Use this only for session feel, pacing, or format preferences.</p>
                  </div>
              </article>
            </div>

            <aside className="step-aside">
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
              <div className="support-panel">
                <p className="kicker">Preference</p>
                <p className="muted">This field is for training feel only, not injuries or general notes.</p>
              </div>
            </aside>
          </div>
        ) : null}

        {currentStep === 3 ? (
          <div className="step-layout">
            <div className="step-main">
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">Restrictions</p>
                  <h2 className="form-section-title">Injuries or restrictions</h2>
                </div>
                <div className="guided-injury-shell">
                  <div className="field compact-gap">
                    <label htmlFor="injuryAreaInput">Pain area or body part</label>
                    <div className="guided-injury-add-row">
                      <input
                        id="injuryAreaInput"
                        value={injuryAreaInput}
                        onChange={(event) => setInjuryAreaInput(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === ",") {
                            event.preventDefault();
                            addGuidedInjuryAreas(injuryAreaInput);
                          }
                        }}
                        placeholder="Type one area, then press Enter or comma"
                      />
                      <button
                        type="button"
                        className="secondary-button guided-injury-add-button"
                        onClick={() => addGuidedInjuryAreas(injuryAreaInput)}
                      >
                        Add area
                      </button>
                    </div>
                    <p className="muted">Each selected area gets its own severity, trend, and restriction details.</p>
                  </div>

                  <div className="guided-injury-chip-row" aria-label="Selected pain areas">
                    {guidedInjuries.length ? (
                      guidedInjuries.map((item) => {
                        const active = item.id === activeGuidedInjuryId;
                        return (
                          <div key={item.id} className={`guided-injury-chip ${active ? "guided-injury-chip-active" : ""}`.trim()}>
                            <button
                              type="button"
                              className="guided-injury-chip-select"
                              onClick={() => setActiveGuidedInjuryId(item.id)}
                              aria-pressed={active}
                            >
                              {item.area || "Untitled area"}
                            </button>
                            <button
                              type="button"
                              className="guided-injury-chip-remove"
                              onClick={() => removeGuidedInjury(item.id)}
                              aria-label={`Remove ${item.area || "injury"}`}
                            >
                              ×
                            </button>
                          </div>
                        );
                      })
                    ) : (
                      <p className="muted">No areas added yet. Add one to start tracking severity and restrictions.</p>
                    )}
                  </div>

                  {activeGuidedInjury ? (
                    <>
                      <div className="guided-injury-editor-header">
                        <div>
                          <p className="kicker">Active area</p>
                          <h3>{activeGuidedInjury.area}</h3>
                        </div>
                        <button
                          type="button"
                          className="ghost-button guided-injury-remove-button"
                          onClick={() => removeGuidedInjury(activeGuidedInjury.id)}
                        >
                          Remove area
                        </button>
                      </div>
                      <div className="form-grid">
                        <div className="field">
                          <label htmlFor="injurySeverity">Current severity</label>
                          <CustomSelect
                            id="injurySeverity"
                            value={activeGuidedInjury.severity}
                            options={INJURY_SEVERITY_OPTIONS}
                            placeholder="Select severity"
                            includeEmptyOption
                            onChange={(value) => updateGuidedInjury("severity", value)}
                          />
                        </div>
                        <div className="field">
                          <label htmlFor="injuryTrend">Current trend</label>
                          <CustomSelect
                            id="injuryTrend"
                            value={activeGuidedInjury.trend}
                            options={INJURY_TREND_OPTIONS}
                            placeholder="Select trend"
                            includeEmptyOption
                            onChange={(value) => updateGuidedInjury("trend", value)}
                          />
                        </div>
                        <div className="field field-span-full">
                          <label htmlFor="injuryAvoid">Movements to avoid</label>
                          <input
                            id="injuryAvoid"
                            value={activeGuidedInjury.avoid}
                            onChange={(event) => updateGuidedInjury("avoid", event.target.value)}
                            placeholder="Heavy overhead pressing, hard sprinting, deep knee flexion"
                          />
                        </div>
                      </div>
                      <div className="field">
                        <label htmlFor="injuryNotes">Extra restriction details</label>
                        <textarea
                          id="injuryNotes"
                          value={activeGuidedInjury.notes}
                          onChange={(event) => updateGuidedInjury("notes", event.target.value)}
                          placeholder="What happened, what irritates it, and anything the planner should work around"
                        />
                      </div>
                    </>
                  ) : null}
                </div>
                <div className="support-panel support-panel-preview compact-gap">
                  <p className="kicker">Planner note preview</p>
                  <div className="guided-injury-preview-list">
                    {guidedInjuries.length ? (
                      guidedInjuries.map((item) => {
                        const summary = buildGuidedInjurySummary(item);
                        return (
                          <p key={item.id} className="muted">
                            • {summary || item.area}
                          </p>
                        );
                      })
                    ) : (
                      <p className="muted">No injury or restriction note added yet.</p>
                    )}
                  </div>
                </div>
              </article>
            </div>

            <aside className="step-aside">
              <div className="support-panel">
                <p className="kicker">Safety</p>
                <p className="muted">Start with body part, severity, trend, and what to avoid. Add free text only for the details that matter.</p>
              </div>
            </aside>
          </div>
        ) : null}

        {currentStep === 4 ? (
          <div className="step-layout">
            <div className="step-main">
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">Target outcomes</p>
                  <h2 className="form-section-title">Key goals</h2>
                </div>
                <CheckboxGroup
                  label="Key Goals"
                  options={KEY_GOAL_OPTIONS}
                  selectedValues={form.key_goals}
                  onToggle={(value) => toggleFieldValue("key_goals", value)}
                />
              </article>
              <article className="step-card">
                <div className="form-section-header">
                  <p className="kicker">Performance gaps</p>
                  <h2 className="form-section-title">Weak areas</h2>
                </div>
                <CheckboxGroup
                  label="Weak Areas"
                  options={WEAK_AREA_OPTIONS}
                  selectedValues={form.weak_areas}
                  onToggle={(value) => toggleFieldValue("weak_areas", value)}
                />
              </article>
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

            <aside className="step-aside">
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
          <div className="step-layout">
            <div className="step-main">
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

            <aside className="step-aside">
              <div className="status-card">
                <p className="status-label">Ready to generate</p>
                <h2 className="plan-summary-title">Final pre-check</h2>
                <p className="muted">Review the saved inputs, then generate.</p>
                <ul className="summary-list">
                  <li>Technical Style must be selected.</li>
                  <li>Fight date must be set.</li>
                  <li>Training Availability needs at least one selected option.</li>
                  <li>Sessions per Week must be at least 1.</li>
                  {availabilityConsistency.hardError ? <li>{availabilityConsistency.hardError}</li> : null}
                  {sparringConsistency.hardError ? <li>{sparringConsistency.hardError}</li> : null}
                </ul>
              </div>
              <div className="support-panel">
                <p className="kicker">Restrictions</p>
                <p className="muted">Injuries or restrictions: {formatValue(form.injuries)}</p>
              </div>
            </aside>
          </div>
        ) : null}

        {message ? <div className="success-banner">{message}</div> : null}
        {error ? <div className="error-banner">{error}</div> : null}

        <div className="form-actions">
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

