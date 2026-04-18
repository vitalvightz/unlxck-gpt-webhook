"use client";

import Link from "next/link";
import { useEffect, useState, useTransition } from "react";

import styles from "@/components/nutrition-pages.module.css";
import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { NutritionSubnav } from "@/components/nutrition-subnav";
import { NutritionWorkspaceHeader } from "@/components/nutrition-workspace-header";
import { getNutritionCurrent, updateNutritionCurrent } from "@/lib/api";
import {
  formatBodyweightDate,
  formatTargetGapLabel,
  formatWeight,
  getLatestBodyweightEntry,
  getLatestEffectiveWeight,
  getSevenDayAverage,
  getTargetGap,
} from "@/lib/nutrition-bodyweight";
import {
  emptyUpdateRequest,
  toCsv,
  toList,
  toNumber,
  toUpdateRequest,
} from "@/lib/nutrition-workspace";
import { TRAINING_AVAILABILITY_OPTIONS } from "@/lib/intake-options";
import type {
  NutritionProfileInput,
  NutritionWorkspaceState,
  NutritionWorkspaceUpdateRequest,
  SessionDayType,
} from "@/lib/types";

const ACTIVITY_OPTIONS = [
  { value: "low", label: "Desk / low movement" },
  { value: "mixed", label: "Mixed" },
  { value: "active_job", label: "Active job" },
];
const WEIGH_IN_OPTIONS = [
  { value: "same_day", label: "Same day" },
  { value: "day_before", label: "Day before" },
  { value: "informal", label: "Informal / none" },
];
const FATIGUE_OPTIONS = [
  { value: "", label: "Select" },
  { value: "low", label: "Low" },
  { value: "moderate", label: "Moderate" },
  { value: "high", label: "High" },
];
const SLEEP_OPTIONS = [
  { value: "", label: "Select" },
  { value: "good", label: "Good" },
  { value: "mixed", label: "Mixed" },
  { value: "poor", label: "Poor" },
];
const WEIGHT_SOURCE_OPTIONS = ["", "manual", "latest_bodyweight_log", "imported"];
const DAY_TYPE_OPTIONS: Array<{ value: Extract<SessionDayType, "hard_spar" | "technical" | "conditioning" | "recovery">; label: string }> = [
  { value: "hard_spar", label: "Hard sparring" },
  { value: "technical", label: "Support work (non-hard)" },
  { value: "conditioning", label: "Conditioning" },
  { value: "recovery", label: "Recovery" },
];
const CORE_FIELD_LABELS: Record<string, string> = {
  sex: "Sex",
  age: "Age",
  height_cm: "Height",
  current_weight_kg: "Current weight",
  target_weight_kg: "Target weight",
};

function sortTrainingDays(values: string[]): string[] {
  const uniqueValues = new Set(values);
  return TRAINING_AVAILABILITY_OPTIONS
    .map((option) => option.value)
    .filter((value) => uniqueValues.has(value));
}

function isSupportedNutritionDayType(value: string | null | undefined): value is Extract<SessionDayType, "hard_spar" | "technical" | "conditioning" | "recovery"> {
  return value === "hard_spar" || value === "technical" || value === "conditioning" || value === "recovery";
}

function normalizeTrainingSelections(
  request: NutritionWorkspaceUpdateRequest,
): NutritionWorkspaceUpdateRequest {
  const nextSessionTypes: Record<string, SessionDayType> = {};

  for (const day of TRAINING_AVAILABILITY_OPTIONS.map((option) => option.value)) {
    const explicitDayType = request.shared_camp_context.session_types_by_day[day];
    if (isSupportedNutritionDayType(explicitDayType)) {
      nextSessionTypes[day] = explicitDayType;
      continue;
    }
    if (request.shared_camp_context.hard_sparring_days.includes(day)) {
      nextSessionTypes[day] = "hard_spar";
      continue;
    }
    if (request.shared_camp_context.support_work_days.includes(day)) {
      nextSessionTypes[day] = "technical";
    }
  }

  const trainingAvailability = sortTrainingDays(Object.keys(nextSessionTypes));
  const hardSparringDays = sortTrainingDays(
    Object.entries(nextSessionTypes)
      .filter(([, value]) => value === "hard_spar")
      .map(([day]) => day),
  );
  const supportWorkDays = sortTrainingDays(
    Object.entries(nextSessionTypes)
      .filter(([, value]) => value === "technical")
      .map(([day]) => day),
  );

  return {
    ...request,
    shared_camp_context: {
      ...request.shared_camp_context,
      hard_sparring_days: hardSparringDays,
      support_work_days: supportWorkDays,
      training_availability: trainingAvailability,
      session_types_by_day: nextSessionTypes,
    },
  };
}

function formatNumber(value: number | null | undefined, unit?: string): string {
  if (value == null) {
    return "Missing in onboarding";
  }
  return unit ? `${value} ${unit}` : String(value);
}

function formatSex(value: NutritionProfileInput["sex"] | null | undefined): string {
  if (value === "male") return "Male";
  if (value === "female") return "Female";
  return "Missing in onboarding";
}

function formatRestrictionsSummary(value: string | null | undefined): string {
  return value?.trim() ? value.trim() : "No restrictions reported in onboarding.";
}

function formatEnumLabel(value: string | null | undefined, fallback: string): string {
  if (!value?.trim()) return fallback;
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function StatusRows({ workspace }: { workspace: NutritionWorkspaceState }) {
  const derived = workspace.derived;
  return (
    <div className="review-detail-list nutrition-review-list">
      {[
        ["Days until fight", derived.days_until_fight != null ? String(derived.days_until_fight) : "Not set"],
        ["Current phase", derived.current_phase_effective || "Not derived yet"],
        ["Cut size", `${derived.weight_cut_pct.toFixed(1)}%`],
      ].map(([label, value]) => (
        <div key={label} className="review-detail-row">
          <p className="review-detail-label">{label}</p>
          <p className="review-detail-value">{value}</p>
        </div>
      ))}
    </div>
  );
}

export function NutritionWorkspaceScreen() {
  const { session, me, refreshMe } = useAppSession();
  const [workspace, setWorkspace] = useState<NutritionWorkspaceState | null>(null);
  const [form, setForm] = useState<NutritionWorkspaceUpdateRequest>(() => emptyUpdateRequest());
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    if (!session?.access_token) return;
    let active = true;
    getNutritionCurrent(session.access_token)
      .then((nextWorkspace) => {
        if (!active) return;
        setWorkspace(nextWorkspace);
        setForm(normalizeTrainingSelections(toUpdateRequest(nextWorkspace)));
      })
      .catch((loadError) => {
        if (!active) return;
        setError(loadError instanceof Error ? loadError.message : "Unable to load nutrition workspace.");
      });
    return () => {
      active = false;
    };
  }, [session?.access_token]);

  function setProfileField(key: keyof NutritionProfileInput, value: unknown) {
    setForm((current) => ({ ...current, nutrition_profile: { ...current.nutrition_profile, [key]: value } }));
  }

  function setSharedField(key: keyof NutritionWorkspaceUpdateRequest["shared_camp_context"], value: unknown) {
    setForm((current) => ({ ...current, shared_camp_context: { ...current.shared_camp_context, [key]: value } }));
  }

  function setSleepQuality(value: string | null) {
    setForm((current) => ({
      ...current,
      nutrition_readiness: {
        ...current.nutrition_readiness,
        sleep_quality: value as NutritionWorkspaceUpdateRequest["nutrition_readiness"]["sleep_quality"],
      },
    }));
  }

  function setDayType(day: string, value: string) {
    setForm((current) => {
      const nextSessionTypes = { ...current.shared_camp_context.session_types_by_day };
      if (!value) {
        delete nextSessionTypes[day];
      } else if (isSupportedNutritionDayType(value)) {
        nextSessionTypes[day] = value;
      }
      return normalizeTrainingSelections({
        ...current,
        shared_camp_context: {
          ...current.shared_camp_context,
          session_types_by_day: nextSessionTypes,
        },
      });
    });
  }

  function handleWeightSourceChange(value: string) {
    const nextValue = value || null;
    setSharedField("current_weight_source", nextValue);
  }

  function handleSave() {
    if (!session?.access_token) return;
    setError(null);
    setMessage(null);
    startTransition(async () => {
      try {
        const nextWorkspace = await updateNutritionCurrent(
          session.access_token,
          normalizeTrainingSelections(form),
        );
        setWorkspace(nextWorkspace);
        setForm(normalizeTrainingSelections(toUpdateRequest(nextWorkspace)));
        await refreshMe();
        setMessage("Nutrition workspace saved.");
      } catch (saveError) {
        setError(saveError instanceof Error ? saveError.message : "Unable to save nutrition workspace.");
      }
    });
  }

  const athleteName = me?.profile.full_name || me?.profile.email || "Nutrition workspace";
  const coreMissingFields = workspace
    ? workspace.derived.missing_required_fields.filter((field) =>
        Object.prototype.hasOwnProperty.call(CORE_FIELD_LABELS, field),
      )
    : [];
  const latestEntry = workspace ? getLatestBodyweightEntry(workspace.nutrition_monitoring.daily_bodyweight_log) : null;
  const latestEffectiveWeight = workspace ? getLatestEffectiveWeight(workspace) : null;
  const rollingAverage = workspace ? getSevenDayAverage(workspace.nutrition_monitoring.daily_bodyweight_log) : null;
  const targetGap = workspace
    ? getTargetGap(latestEffectiveWeight, workspace.shared_camp_context.target_weight_kg)
    : null;

  return (
    <RequireAuth>
      <section className="panel">
        <NutritionWorkspaceHeader
          athleteName={athleteName}
          title="Nutrition workspace"
          description="Keep camp setup, readiness, and nutrition parameters here. Restrictions stay anchored to onboarding, and the dedicated bodyweight log now lives on its own fight-lab screen."
        />
        <NutritionSubnav />

        {!workspace ? (
          <section className="support-panel loading-card"><p className="muted">Loading nutrition workspace.</p></section>
        ) : (
          <div className="nutrition-page-grid">
            <div className="nutrition-main-column">

              {/* ── Group 1: Athlete foundation ───────────────────── */}
              <div className="nutrition-group">
                <p className="nutrition-group-label">Athlete foundation</p>
                <article className="step-card nutrition-section">
                  <div className="form-section-header">
                    <p className="kicker">Overview</p>
                    <h2 className="form-section-title">Status</h2>
                  </div>
                  <StatusRows workspace={workspace} />
                  <p className="muted">
                    Foundation status: <strong>{workspace.derived.foundation_status}</strong>
                    {workspace.derived.missing_required_fields.length
                      ? ` - Missing: ${workspace.derived.missing_required_fields.join(", ")}`
                      : ""}
                  </p>
                </article>

                <article className="step-card nutrition-section">
                  <div className="form-section-header">
                    <p className="kicker">Basics</p>
                    <h2 className="form-section-title">Athlete details</h2>
                  </div>
                  <div className="review-detail-list nutrition-review-list">
                    {[
                      ["Sex", formatSex(workspace.nutrition_profile.sex)],
                      ["Age", formatNumber(workspace.nutrition_profile.age)],
                      ["Height", formatNumber(workspace.nutrition_profile.height_cm, "cm")],
                      ["Current weight", formatNumber(workspace.shared_camp_context.current_weight_kg, "kg")],
                      ["Target weight", formatNumber(workspace.shared_camp_context.target_weight_kg, "kg")],
                    ].map(([label, value]) => (
                      <div key={label} className="review-detail-row">
                        <p className="review-detail-label">{label}</p>
                        <p className="review-detail-value">{value}</p>
                      </div>
                    ))}
                  </div>
                  <p className="muted">These details come from onboarding so you only have to enter them once.</p>
                  {coreMissingFields.length ? (
                    <p className="muted">
                      Still missing in onboarding: {coreMissingFields.map((field) => CORE_FIELD_LABELS[field]).join(", ")}.
                    </p>
                  ) : null}
                  <div className="plan-summary-actions">
                    <Link href="/onboarding" className="ghost-button">Edit in onboarding</Link>
                  </div>
                </article>

                <article className="step-card nutrition-section">
                  <div className="form-section-header">
                    <p className="kicker">Basics</p>
                    <h2 className="form-section-title">Restrictions</h2>
                  </div>
                  <div className="review-detail-list nutrition-review-list">
                    {[
                      ["Injuries / restrictions", formatRestrictionsSummary(workspace.shared_camp_context.injuries)],
                      ["Restriction level", formatEnumLabel(workspace.shared_camp_context.training_restriction_level, "Not set")],
                    ].map(([label, value]) => (
                      <div key={label} className="review-detail-row">
                        <p className="review-detail-label">{label}</p>
                        <p className="review-detail-value">{value}</p>
                      </div>
                    ))}
                  </div>
                  <p className="muted">Restrictions live in onboarding so your nutrition workspace stays aligned with the core athlete profile.</p>
                  <div className="plan-summary-actions">
                    <Link href="/onboarding" className="ghost-button">Edit in onboarding</Link>
                  </div>
                </article>
              </div>

              {/* ── Group 2: Bodyweight ───────────────────────────── */}
              <div className="nutrition-group">
                <p className="nutrition-group-label">Bodyweight</p>
                <article className={`step-card nutrition-section ${styles.previewCard}`}>
                  <div className={styles.previewHeader}>
                    <div className={styles.previewHeaderCopy}>
                      <p className="kicker">Bodyweight</p>
                      <h2 className="form-section-title">Preview</h2>
                      <p className="muted">Latest readout lives here. Full logging, trend review, and history edits now happen in the dedicated bodyweight lab.</p>
                    </div>
                    <Link href="/nutrition/bodyweight-log" className="cta">Open bodyweight log</Link>
                  </div>

                  <div className={styles.previewGrid}>
                    <div className={styles.previewMetric}>
                      <p className={styles.previewMetricLabel}>Latest logged weight</p>
                      <p className={styles.previewMetricValue}>{formatWeight(latestEntry?.weight_kg)}</p>
                    </div>
                    <div className={styles.previewMetric}>
                      <p className={styles.previewMetricLabel}>Target gap</p>
                      <p className={styles.previewMetricValue}>{formatTargetGapLabel(targetGap)}</p>
                    </div>
                    <div className={styles.previewMetric}>
                      <p className={styles.previewMetricLabel}>7-day average</p>
                      <p className={styles.previewMetricValue}>{formatWeight(rollingAverage)}</p>
                    </div>
                    <div className={styles.previewMetric}>
                      <p className={styles.previewMetricLabel}>Last entry</p>
                      <p className={styles.previewMetricValue}>{formatBodyweightDate(latestEntry?.date ?? null)}</p>
                    </div>
                  </div>

                  <div className={styles.previewFooter}>
                    <p className="muted">
                      {latestEntry
                        ? "Use the dedicated log for fast entry, trend review, and deliberate inline edits."
                        : "No weigh-ins logged yet. Start with the dedicated log to establish your trend line."}
                    </p>
                  </div>
                </article>
              </div>

              {/* ── Group 3: Fight setup ──────────────────────────── */}
              <div className="nutrition-group">
                <p className="nutrition-group-label">Fight setup</p>
                <article className="step-card nutrition-section">
                  <div className="form-section-header">
                    <p className="kicker">Weight</p>
                    <h2 className="form-section-title">Fight setup</h2>
                  </div>
                  <div className="form-grid">
                    <div className="field">
                      <label>Fight date</label>
                      <input
                        type="date"
                        value={form.shared_camp_context.fight_date ?? ""}
                        onChange={(event) => setSharedField("fight_date", event.target.value)}
                      />
                    </div>
                    <div className="field">
                      <label>Weigh-in type</label>
                      <select
                        value={form.shared_camp_context.weigh_in_type ?? ""}
                        onChange={(event) => setSharedField("weigh_in_type", event.target.value || null)}
                      >
                        <option value="">Select</option>
                        {WEIGH_IN_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                      </select>
                    </div>
                    <div className="field">
                      <label>Weigh-in time</label>
                      <input
                        type="time"
                        value={form.shared_camp_context.weigh_in_time ?? ""}
                        onChange={(event) => setSharedField("weigh_in_time", event.target.value)}
                      />
                    </div>
                    <div className="field">
                      <label>Current weight source</label>
                      <select
                        value={form.shared_camp_context.current_weight_source ?? ""}
                        onChange={(event) => handleWeightSourceChange(event.target.value)}
                      >
                        {WEIGHT_SOURCE_OPTIONS.map((value) => (
                          <option key={value || "empty"} value={value}>{value || "Select"}</option>
                        ))}
                      </select>
                      <p className="muted">This stays tied to onboarding/current weight data and still respects latest-log matching behavior.</p>
                    </div>
                    <div className="field">
                      <label>Weight recorded at</label>
                      <input
                        type="datetime-local"
                        value={form.shared_camp_context.current_weight_recorded_at ?? ""}
                        onChange={(event) => setSharedField("current_weight_recorded_at", event.target.value)}
                      />
                    </div>
                    <div className="field">
                      <label>Rounds format</label>
                      <input
                        value={form.shared_camp_context.rounds_format ?? ""}
                        onChange={(event) => setSharedField("rounds_format", event.target.value)}
                      />
                    </div>
                  </div>
                </article>
              </div>

              {/* ── Group 4: Readiness & nutrition ───────────────── */}
              <div className="nutrition-group">
                <p className="nutrition-group-label">Readiness &amp; nutrition</p>
                <article className="step-card nutrition-section">
                  <div className="form-section-header">
                    <p className="kicker">Readiness</p>
                    <h2 className="form-section-title">Schedule and readiness</h2>
                  </div>
                  <div className="form-grid">
                    <div className="field">
                      <label>Sessions per week</label>
                      <input
                        type="number"
                        min="1"
                        max="6"
                        value={form.shared_camp_context.weekly_training_frequency ?? ""}
                        onChange={(event) => setSharedField("weekly_training_frequency", toNumber(event.target.value))}
                      />
                    </div>
                    <div className="field">
                      <label>Fatigue level</label>
                      <select
                        value={form.shared_camp_context.fatigue_level ?? ""}
                        onChange={(event) => setSharedField("fatigue_level", event.target.value || null)}
                      >
                        {FATIGUE_OPTIONS.map((option) => (
                          <option key={option.value || "empty"} value={option.value}>{option.label}</option>
                        ))}
                      </select>
                    </div>
                    <div className="field">
                      <label>Sleep quality</label>
                      <select
                        value={form.nutrition_readiness.sleep_quality ?? ""}
                        onChange={(event) => setSleepQuality(event.target.value || null)}
                      >
                        {SLEEP_OPTIONS.map((option) => (
                          <option key={option.value || "empty"} value={option.value}>{option.label}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div className="nutrition-daytype-grid">
                    {TRAINING_AVAILABILITY_OPTIONS.map((option) => (
                      <div key={option.value} className="field">
                        <label>{option.label} day type</label>
                        <select
                          value={form.shared_camp_context.session_types_by_day[option.value] ?? ""}
                          onChange={(event) => setDayType(option.value, event.target.value)}
                        >
                          <option value="">Off / not scheduled</option>
                          {DAY_TYPE_OPTIONS.map((dayTypeOption) => (
                            <option key={dayTypeOption.value} value={dayTypeOption.value}>{dayTypeOption.label}</option>
                          ))}
                        </select>
                      </div>
                    ))}
                  </div>
                  <p className="muted">Pick the day type directly for each weekday. Hard sparring and Support Work Days (non-hard training / S&C-compatible slots) still feed the saved planning fields automatically, while conditioning and recovery stay available here too.</p>
                </article>

                <article className="step-card nutrition-section">
                  <div className="form-section-header">
                    <p className="kicker">Nutrition</p>
                    <h2 className="form-section-title">Nutrition parameters</h2>
                  </div>
                  <div className="form-grid">
                    <div className="field">
                      <label>Daily activity</label>
                      <select
                        value={form.nutrition_profile.daily_activity_level ?? ""}
                        onChange={(event) => setProfileField("daily_activity_level", event.target.value || null)}
                      >
                        <option value="">Select</option>
                        {ACTIVITY_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                      </select>
                    </div>
                    <div className="field">
                      <label>Dietary restrictions</label>
                      <input
                        value={toCsv(form.nutrition_profile.dietary_restrictions)}
                        onChange={(event) => setProfileField("dietary_restrictions", toList(event.target.value))}
                      />
                    </div>
                    <div className="field">
                      <label>Meals per day</label>
                      <input
                        type="number"
                        min="1"
                        max="8"
                        value={form.nutrition_profile.meals_per_day_preference ?? ""}
                        onChange={(event) => setProfileField("meals_per_day_preference", toNumber(event.target.value))}
                      />
                    </div>
                    <div className="field">
                      <label>Caffeine use</label>
                      <select
                        value={form.nutrition_profile.caffeine_use == null ? "" : form.nutrition_profile.caffeine_use ? "yes" : "no"}
                        onChange={(event) => setProfileField("caffeine_use", event.target.value ? event.target.value === "yes" : null)}
                      >
                        <option value="">Select</option>
                        <option value="yes">Yes</option>
                        <option value="no">No</option>
                      </select>
                    </div>
                    <div className="field">
                      <label>Supplements</label>
                      <input
                        value={toCsv(form.nutrition_profile.supplement_use)}
                        onChange={(event) => setProfileField("supplement_use", toList(event.target.value))}
                      />
                    </div>
                  </div>
                  <p className="muted">This workspace supports macro and micro planning inputs, not meal-by-meal food choices. We can add athlete food-level controls later if needed.</p>
                </article>
              </div>

            </div>

            <aside className="nutrition-side-column">
              <article className="support-panel">
                <p className="kicker">Flags</p>
                <p className="muted">{workspace.derived.readiness_flags.length ? workspace.derived.readiness_flags.join(", ") : "No active readiness flags."}</p>
              </article>
              <article className="support-panel">
                <p className="kicker">Bodyweight</p>
                <p className="muted">Open the dedicated log for premium trend review, quick add, and historical edits without leaving the Nutrition workspace.</p>
                <Link href="/nutrition/bodyweight-log" className="ghost-button">Go to log</Link>
              </article>
            </aside>
          </div>
        )}

        {message ? <div className="success-banner athlete-motion-slot athlete-motion-status">{message}</div> : null}
        {error ? <div className="error-banner athlete-motion-slot athlete-motion-status">{error}</div> : null}

        <div className="nutrition-sticky-save">
          <button type="button" className="cta" onClick={handleSave} disabled={isPending || !workspace}>
            {isPending ? "Saving..." : "Save nutrition workspace"}
          </button>
        </div>
      </section>
    </RequireAuth>
  );
}
