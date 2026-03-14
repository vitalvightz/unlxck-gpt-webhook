"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

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

function numberOrNull(value: string): number | null {
  if (!value.trim()) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "Unspecified";
  }
  return String(value);
}

function StepPills({ currentStep }: { currentStep: number }) {
  return (
    <div className="step-progress" aria-label="Onboarding progress">
      {steps.map((label, index) => {
        const statusClass = index < currentStep ? "step-pill-complete" : index === currentStep ? "step-pill-active" : "";
        const statusText = index < currentStep ? "Complete" : index === currentStep ? "Current" : "Upcoming";

        return (
          <div key={label} className={`step-pill ${statusClass}`.trim()}>
            <span className="step-pill-index">{String(index + 1).padStart(2, "0")}</span>
            <div>
              <div className="step-pill-title">{label}</div>
              <p className="step-pill-meta">{statusText}</p>
            </div>
          </div>
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
  const [hydrated, setHydrated] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const detectedTimeZone = detectDeviceTimeZone() || form.athlete.athlete_timezone || "Automatic";
  const recordHasError = !isValidRecordFormat(form.athlete.record ?? "");

  useEffect(() => {
    if (!me || hydrated) {
      return;
    }
    setForm(syncDeviceFields(hydratePlanRequest(me)));
    const savedStep = Number((me.profile.onboarding_draft as { current_step?: number } | null)?.current_step ?? 0);
    setCurrentStep(Number.isFinite(savedStep) ? Math.min(Math.max(savedStep, 0), steps.length - 1) : 0);
    setHydrated(true);
  }, [hydrated, me]);

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

  function toggleFieldValue(key: "training_availability" | "equipment_access" | "key_goals" | "weak_areas", value: string) {
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
      try {
        await persistDraft(nextStep);
        setCurrentStep(nextStep);
      } catch (draftError) {
        setError(draftError instanceof Error ? draftError.message : "Unable to save progress.");
      }
    });
  }

  function handleBack() {
    setCurrentStep((step) => Math.max(step - 1, 0));
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

  const technicalStyleLabel = getOptionLabel(TECHNICAL_STYLE_OPTIONS, form.athlete.technical_style[0] ?? "") || "Unspecified";
  const tacticalStyleLabel = getOptionLabel(TACTICAL_STYLE_OPTIONS, form.athlete.tactical_style[0] ?? "") || "Unspecified";
  const statusLabel = getOptionLabel(PROFESSIONAL_STATUS_OPTIONS, form.athlete.professional_status ?? "") || "Unspecified";
  const selectedTrainingAvailability = getOptionLabels(TRAINING_AVAILABILITY_OPTIONS, form.training_availability).join(", ") || "Unspecified";
  const selectedEquipmentAccess = getOptionLabels(EQUIPMENT_ACCESS_OPTIONS, form.equipment_access).join(", ") || "Unspecified";
  const selectedGoals = getOptionLabels(KEY_GOAL_OPTIONS, form.key_goals).join(", ") || "Unspecified";
  const selectedWeakAreas = getOptionLabels(WEAK_AREA_OPTIONS, form.weak_areas).join(", ") || "Unspecified";

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

        <StepPills currentStep={currentStep} />

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
                  </div>
                  <div className="field">
                    <label htmlFor="targetWeightKg">Target weight (kg)</label>
                    <input id="targetWeightKg" type="number" min="0" step="0.1" value={form.athlete.target_weight_kg ?? ""} onChange={(event) => updateAthlete("target_weight_kg", numberOrNull(event.target.value))} />
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
                      inputMode="numeric"
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
                  <li>Professional Status: {statusLabel}</li>
                  <li>Record: {formatValue(form.athlete.record)}</li>
                </ul>
              </div>
              <div className="support-panel">
                <div className="form-section-header">
                  <p className="kicker">Device time</p>
                  <h2 className="form-section-title">Automatic handling</h2>
                </div>
                <p className="muted">Device time is used automatically: <strong>{detectedTimeZone}</strong>.</p>
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
                    <label htmlFor="roundsFormat">Rounds</label>
                    <input id="roundsFormat" value={form.rounds_format ?? ""} onChange={(event) => updateField("rounds_format", event.target.value)} />
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
                      options={[
                        { label: "Low", value: "low" },
                        { label: "Moderate", value: "moderate" },
                        { label: "High", value: "high" },
                      ]}
                      placeholder="Select fatigue level"
                      onChange={(value) => updateField("fatigue_level", value)}
                    />
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
                  <label htmlFor="trainingPreference">Training Preference</label>
                  <textarea id="trainingPreference" value={form.training_preference ?? ""} onChange={(event) => updateField("training_preference", event.target.value)} placeholder="Anything about session style, equipment, or pacing you prefer" />
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
                  <li>Equipment Access: {selectedEquipmentAccess}</li>
                </ul>
              </div>
              <div className="support-panel">
                <p className="kicker">Preference</p>
                <p className="muted">Use natural language for session feel, equipment constraints, or pacing.</p>
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
                <div className="field">
                  <label htmlFor="injuries">Injuries or restrictions</label>
                  <textarea id="injuries" value={form.injuries ?? ""} onChange={(event) => updateField("injuries", event.target.value)} placeholder="Shoulder irritation, lower-back stiffness, avoid heavy overhead pressing" />
                </div>
              </article>
            </div>

            <aside className="step-aside">
              <div className="support-panel">
                <p className="kicker">Safety</p>
                <p className="muted">Specific notes help the planner adapt safely.</p>
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
                  <p className="kicker">Mindset and notes</p>
                  <h2 className="form-section-title">Additional context</h2>
                </div>
                <div className="form-grid">
                  <div className="field">
                    <label htmlFor="mindsetChallenges">Mindset challenges</label>
                    <textarea id="mindsetChallenges" value={form.mindset_challenges ?? ""} onChange={(event) => updateField("mindset_challenges", event.target.value)} />
                  </div>
                  <div className="field">
                    <label htmlFor="notes">Notes</label>
                    <textarea id="notes" value={form.notes ?? ""} onChange={(event) => updateField("notes", event.target.value)} />
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
                  <li>Mindset challenges: {formatValue(form.mindset_challenges)}</li>
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
                <div className="review-grid">
                  <article className="review-card">
                    <div className="review-card-header">
                      <p className="kicker">Profile</p>
                      <h3 className="review-card-title">Athlete profile</h3>
                    </div>
                    <ul className="summary-list">
                      <li>Name: {formatValue(form.athlete.full_name)}</li>
                      <li>Technical Style: {technicalStyleLabel}</li>
                      <li>Tactical Style: {tacticalStyleLabel}</li>
                      <li>Professional Status: {statusLabel}</li>
                      <li>Record: {formatValue(form.athlete.record)}</li>
                    </ul>
                  </article>
                  <article className="review-card">
                    <div className="review-card-header">
                      <p className="kicker">Fight context</p>
                      <h3 className="review-card-title">Camp setup</h3>
                    </div>
                    <ul className="summary-list">
                      <li>Fight date: {formatValue(form.fight_date)}</li>
                      <li>Rounds: {formatValue(form.rounds_format)}</li>
                      <li>Sessions per Week: {formatValue(form.weekly_training_frequency)}</li>
                      <li>Fatigue level: {formatValue(form.fatigue_level || "moderate")}</li>
                    </ul>
                  </article>
                  <article className="review-card">
                    <div className="review-card-header">
                      <p className="kicker">Training</p>
                      <h3 className="review-card-title">Availability and equipment</h3>
                    </div>
                    <ul className="summary-list">
                      <li>Training Availability: {selectedTrainingAvailability}</li>
                      <li>Equipment Access: {selectedEquipmentAccess}</li>
                      <li>Training Preference: {formatValue(form.training_preference)}</li>
                    </ul>
                  </article>
                  <article className="review-card">
                    <div className="review-card-header">
                      <p className="kicker">Performance</p>
                      <h3 className="review-card-title">Goals and weak areas</h3>
                    </div>
                    <ul className="summary-list">
                      <li>Key Goals: {selectedGoals}</li>
                      <li>Weak Areas: {selectedWeakAreas}</li>
                      <li>Mindset challenges: {formatValue(form.mindset_challenges)}</li>
                      <li>Notes: {formatValue(form.notes)}</li>
                    </ul>
                  </article>
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
                  <li>Device time is applied automatically: {detectedTimeZone}.</li>
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

