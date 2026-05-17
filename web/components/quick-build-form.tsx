"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { CustomSelect } from "@/components/custom-select";
import { saveOnboardingDraft } from "@/lib/api";
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
  quickBuildToPlanRequest,
  validateQuickBuildInput,
  type QuickBuildInput,
  type QuickBuildValidationErrors,
} from "@/lib/quick-build";

const WEEKLY_FREQUENCY_OPTIONS: IntakeOption[] = Array.from({ length: 6 }, (_, index) => ({
  label: String(index + 1),
  value: String(index + 1),
}));

type ChipMultiSelectProps = {
  label: string;
  options: IntakeOption[];
  selectedValues: string[];
  onToggle: (value: string) => void;
  capDisabledReason?: string;
  disableAdditionalSelections?: boolean;
};

function ChipMultiSelect({
  label,
  options,
  selectedValues,
  onToggle,
  capDisabledReason,
  disableAdditionalSelections = false,
}: ChipMultiSelectProps) {
  return (
    <div className="field">
      <span className="checkbox-group-label">{label}</span>
      <div className="checkbox-grid">
        {options.map((option) => {
          const checked = selectedValues.includes(option.value);
          const capDisabled = disableAdditionalSelections && !checked;
          return (
            <label
              key={option.value}
              className={`checkbox-card ${checked ? "checkbox-card-checked" : ""} ${capDisabled ? "checkbox-card-disabled" : ""}`.trim()}
              aria-disabled={capDisabled}
              title={capDisabled ? capDisabledReason : undefined}
            >
              <input
                type="checkbox"
                checked={checked}
                disabled={capDisabled}
                onChange={() => onToggle(option.value)}
              />
              <span className="checkbox-card-copy">
                <span className="checkbox-card-title">{option.label}</span>
                {capDisabled && capDisabledReason ? (
                  <span className="checkbox-card-tag">{capDisabledReason}</span>
                ) : null}
              </span>
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
    <p className="muted" role="alert" style={{ color: "var(--color-error, #c0392b)" }}>
      {message}
    </p>
  );
}

function QuickBuildFormInner() {
  const router = useRouter();
  const { me, session, replaceMe } = useAppSession();
  const [input, setInput] = useState<QuickBuildInput>(() => emptyQuickBuildInput(me?.profile.full_name ?? ""));
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [showErrors, setShowErrors] = useState(false);
  const [isPending, startTransition] = useTransition();

  const errors: QuickBuildValidationErrors = useMemo(() => validateQuickBuildInput(input), [input]);
  const parsedRounds = parseRoundsFormat(input.rounds_format);

  function patch<K extends keyof QuickBuildInput>(key: K, value: QuickBuildInput[K]) {
    setInput((current) => ({ ...current, [key]: value }));
  }

  function toggleField(key: keyof Pick<QuickBuildInput, "technical_style" | "tactical_style" | "training_availability" | "equipment_access" | "key_goals" | "weak_areas">, value: string) {
    setInput((current) => ({
      ...current,
      [key]: toggleListValue(current[key], value),
    }));
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitError(null);
    const currentErrors = validateQuickBuildInput(input);
    if (Object.keys(currentErrors).length > 0) {
      setShowErrors(true);
      return;
    }
    if (!session?.access_token) {
      setSubmitError("Sign in again to generate a plan.");
      return;
    }

    startTransition(async () => {
      try {
        const planRequest = quickBuildToPlanRequest(input);
        const draft = {
          ...planRequest,
          current_step: 0,
          plan_source: "quick_build" as const,
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
        if (me) {
          replaceMe({
            ...me,
            profile: {
              ...me.profile,
              full_name: planRequest.athlete.full_name,
              technical_style: planRequest.athlete.technical_style,
              tactical_style: planRequest.athlete.tactical_style,
              athlete_timezone: planRequest.athlete.athlete_timezone ?? me.profile.athlete_timezone,
              onboarding_draft: draft,
            },
          });
        }
        router.push("/generate");
      } catch (err) {
        setSubmitError(err instanceof Error ? err.message : "Could not save Quick Build draft.");
      }
    });
  }

  const visibleError = (key: keyof QuickBuildValidationErrors): string | undefined =>
    showErrors ? errors[key] : undefined;

  return (
    <form onSubmit={handleSubmit} className="onboarding-form">
      <section className="hero-panel">
        <p className="eyebrow">Quick Build</p>
        <h1 className="hero-title">Generate a plan in about two minutes.</h1>
        <p className="muted">
          Quick Build uses safe defaults for fatigue, sparring intensity, and goal prioritization. Use Detailed Intake for full
          control — you can also refine this plan afterwards.
        </p>
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
            required
          />
          <FieldError message={visibleError("full_name")} />
        </div>
        <ChipMultiSelect
          label="Technical style"
          options={TECHNICAL_STYLE_OPTIONS}
          selectedValues={input.technical_style}
          onToggle={(value) => toggleField("technical_style", value)}
        />
        <FieldError message={visibleError("technical_style")} />
        <ChipMultiSelect
          label="Tactical style (optional)"
          options={TACTICAL_STYLE_OPTIONS}
          selectedValues={input.tactical_style}
          onToggle={(value) => toggleField("tactical_style", value)}
        />
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
              onChange={(event) =>
                setInput((current) => ({
                  ...current,
                  no_scheduled_fight: event.target.checked,
                  fight_date: event.target.checked ? "" : current.fight_date,
                }))
              }
            />
            <span className="checkbox-card-copy">
              <span className="checkbox-card-title">No scheduled fight</span>
              <span className="checkbox-card-tag">Open camp / general prep</span>
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
        <ChipMultiSelect
          label="Days you can train"
          options={TRAINING_AVAILABILITY_OPTIONS}
          selectedValues={input.training_availability}
          onToggle={(value) => toggleField("training_availability", value)}
        />
        <div className="field">
          <label htmlFor="qb-weekly-frequency">Sessions per week</label>
          <CustomSelect
            id="qb-weekly-frequency"
            value={String(input.weekly_training_frequency)}
            options={WEEKLY_FREQUENCY_OPTIONS}
            placeholder="Sessions"
            onChange={(value) => patch("weekly_training_frequency", Number(value) || 1)}
          />
          <FieldError message={visibleError("weekly_training_frequency")} />
          <FieldError message={visibleError("training_availability")} />
        </div>
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
        <ChipMultiSelect
          label={`Key goals (pick up to ${QUICK_BUILD_KEY_GOAL_CAP})`}
          options={KEY_GOAL_OPTIONS}
          selectedValues={input.key_goals}
          onToggle={(value) => toggleField("key_goals", value)}
          disableAdditionalSelections={input.key_goals.length >= QUICK_BUILD_KEY_GOAL_CAP}
          capDisabledReason={`Limit ${QUICK_BUILD_KEY_GOAL_CAP}`}
        />
        <FieldError message={visibleError("key_goals")} />
        <ChipMultiSelect
          label={`Weak areas (optional, up to ${QUICK_BUILD_WEAK_AREA_CAP})`}
          options={WEAK_AREA_OPTIONS}
          selectedValues={input.weak_areas}
          onToggle={(value) => toggleField("weak_areas", value)}
          disableAdditionalSelections={input.weak_areas.length >= QUICK_BUILD_WEAK_AREA_CAP}
          capDisabledReason={`Limit ${QUICK_BUILD_WEAK_AREA_CAP}`}
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
          <label htmlFor="qb-injuries">Anything the planner should avoid</label>
          <textarea
            id="qb-injuries"
            value={input.injuries}
            onChange={(event) => patch("injuries", event.target.value)}
            placeholder="Example: right shoulder tweak — avoid heavy overhead pressing for the first two weeks."
          />
        </div>
      </article>

      <div className="form-actions">
        <p className="muted">Refine fatigue, sparring days, and detailed weaknesses later from the plan page.</p>
        {submitError ? <FieldError message={submitError} /> : null}
        <div className="plan-summary-actions">
          <button type="submit" className="cta" disabled={isPending}>
            {isPending ? "Saving…" : "Generate Plan"}
          </button>
          <Link href="/onboarding" className="ghost-button">
            Use Detailed Intake instead
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
