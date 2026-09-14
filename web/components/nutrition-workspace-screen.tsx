"use client";

import Link from "next/link";
import { useEffect, useState, useTransition } from "react";

import styles from "@/components/nutrition-pages.module.css";
import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { NutritionSubnav } from "@/components/nutrition-subnav";
import { NutritionWorkspaceHeader } from "@/components/nutrition-workspace-header";
import { NutritionWorkspaceSkeleton } from "@/components/skeleton";
import { SafetyNote } from "@/components/safety-note";
import { useToast } from "@/components/toast-provider";
import { WEIGHT_CUT_SAFETY } from "@/lib/safety-copy";
import { LevelSlider, type LevelValue } from "@/components/rating-controls";
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
import { useTranslations as useAppTranslations } from "next-intl";
import { translateUiText } from "@/i18n/ui-text";

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
    return "Missing in Advanced Intake";
  }
  return unit ? `${value} ${unit}` : String(value);
}

function formatSex(value: NutritionProfileInput["sex"] | null | undefined): string {
  if (value === "male") return "Male";
  if (value === "female") return "Female";
  return "Missing in Advanced Intake";
}

function formatRestrictionsSummary(value: string | null | undefined): string {
  return value?.trim() ? value.trim() : "No restrictions reported in Advanced Intake.";
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
    const appText = useAppTranslations("AppText");
  const { session, me, refreshMe } = useAppSession();
  // Server-derived age band. Under-18s get no weight-cut feature, so the target
  // weight and the gap-to-target derived from it are not shown; the backend
  // strips the stored value too.
  const isMinorAthlete = Boolean(me?.profile.is_minor);
  const { showToast } = useToast();
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
        showToast("Nutrition workspace saved.", { tone: "success" });
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
  const targetGap =
    workspace && !isMinorAthlete
      ? getTargetGap(latestEffectiveWeight, workspace.shared_camp_context.target_weight_kg)
      : null;

  return (
    <RequireAuth>
      <section className="panel">
        <NutritionWorkspaceHeader
          athleteName={athleteName}
          title={appText("text_02207fbaeaef")}
          description={appText("text_33c9db35137d")}
        />
        <NutritionSubnav />
        <SafetyNote tone="warning">{WEIGHT_CUT_SAFETY}</SafetyNote>

        {!workspace ? (
          <NutritionWorkspaceSkeleton />
        ) : (
          <div className="nutrition-page-grid">
            <div className="nutrition-main-column">

              {/* ── Group 1: Athlete foundation ───────────────────── */}
              <div className="nutrition-group">
                <p className="nutrition-group-label">{appText("text_6939d7817a61")}</p>
                <article className="step-card nutrition-section">
                  <div className="form-section-header">
                    <p className="kicker">{appText("text_d4b1ea5708dd")}</p>
                    <h2 className="form-section-title">{appText("text_920e413c7d41")}</h2>
                  </div>
                  <StatusRows workspace={workspace} />
                  <p className="muted">
                    {appText("text_e8baf392f100")}<strong>{workspace.derived.foundation_status}</strong>
                    {workspace.derived.missing_required_fields.length
                      ? ` - Missing: ${workspace.derived.missing_required_fields.join(", ")}`
                      : ""}
                  </p>
                </article>

                <article className="step-card nutrition-section">
                  <div className="form-section-header">
                    <p className="kicker">{appText("text_8fdd2ee8475e")}</p>
                    <h2 className="form-section-title">{appText("text_39ae4d0ac9cc")}</h2>
                  </div>
                  <div className="review-detail-list nutrition-review-list">
                    {[
                      ["Sex", formatSex(workspace.nutrition_profile.sex)],
                      ["Age", formatNumber(workspace.nutrition_profile.age)],
                      ["Height", formatNumber(workspace.nutrition_profile.height_cm, "cm")],
                      ["Current weight", formatNumber(workspace.shared_camp_context.current_weight_kg, "kg")],
                      ...(isMinorAthlete
                        ? []
                        : [
                            [
                              "Target weight",
                              formatNumber(workspace.shared_camp_context.target_weight_kg, "kg"),
                            ] as [string, string],
                          ]),
                    ].map(([label, value]) => (
                      <div key={label} className="review-detail-row">
                        <p className="review-detail-label">{label}</p>
                        <p className="review-detail-value">{value}</p>
                      </div>
                    ))}
                  </div>
                  <p className="muted">{appText("text_a8dbc22b8ae3")}</p>
                  {coreMissingFields.length ? (
                    <p className="muted">
                      {appText("text_e29a6e2dda5d")}{coreMissingFields.map((field) => CORE_FIELD_LABELS[field]).join(", ")}{appText("text_cdb4ee2aea69")}</p>
                  ) : null}
                  <div className="plan-summary-actions">
                    <Link href="/onboarding" className="ghost-button">{appText("text_efa187b19e60")}</Link>
                  </div>
                </article>

                <article className="step-card nutrition-section">
                  <div className="form-section-header">
                    <p className="kicker">{appText("text_8fdd2ee8475e")}</p>
                    <h2 className="form-section-title">{appText("text_25ed77282d99")}</h2>
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
                  <p className="muted">{appText("text_55337493f70b")}</p>
                  <div className="plan-summary-actions">
                    <Link href="/onboarding" className="ghost-button">{appText("text_efa187b19e60")}</Link>
                  </div>
                </article>
              </div>

              {/* ── Group 2: Bodyweight ───────────────────────────── */}
              <div className="nutrition-group">
                <p className="nutrition-group-label">{appText("text_581d1b4da4c0")}</p>
                <article className={`step-card nutrition-section ${styles.previewCard}`}>
                  <div className={styles.previewHeader}>
                    <div className={styles.previewHeaderCopy}>
                      <p className="kicker">{appText("text_581d1b4da4c0")}</p>
                      <h2 className="form-section-title">{appText("text_324b134f57c7")}</h2>
                      <p className="muted">{appText("text_cd386873cb9f")}</p>
                    </div>
                    <Link href="/nutrition/bodyweight-log" className="cta">{appText("text_952703665385")}</Link>
                  </div>

                  <div className={styles.previewGrid}>
                    <div className={styles.previewMetric}>
                      <p className={styles.previewMetricLabel}>{appText("text_dd40bf3eb6d2")}</p>
                      <p className={styles.previewMetricValue}>{formatWeight(latestEntry?.weight_kg)}</p>
                    </div>
                    <div className={styles.previewMetric}>
                      <p className={styles.previewMetricLabel}>{appText("text_066bc4277daf")}</p>
                      <p className={styles.previewMetricValue}>{formatTargetGapLabel(targetGap)}</p>
                    </div>
                    <div className={styles.previewMetric}>
                      <p className={styles.previewMetricLabel}>{appText("text_f7da9e525d6f")}</p>
                      <p className={styles.previewMetricValue}>{formatWeight(rollingAverage)}</p>
                    </div>
                    <div className={styles.previewMetric}>
                      <p className={styles.previewMetricLabel}>{appText("text_ffe191a34207")}</p>
                      <p className={styles.previewMetricValue}>{formatBodyweightDate(latestEntry?.date ?? null)}</p>
                    </div>
                  </div>

                  <div className={styles.previewFooter}>
                    <p className="muted">
                      {latestEntry
                        ? appText("text_d9997ba36bd0")
                        : appText("text_f1e8717f9e26")}
                    </p>
                  </div>
                </article>
              </div>

              {/* ── Group 3: Fight setup ──────────────────────────── */}
              <div className="nutrition-group">
                <p className="nutrition-group-label">{appText("text_b05560b31ea5")}</p>
                <article className="step-card nutrition-section">
                  <div className="form-section-header">
                    <p className="kicker">{appText("text_81d27ef6d503")}</p>
                    <h2 className="form-section-title">{appText("text_b05560b31ea5")}</h2>
                  </div>
                  <div className="form-grid">
                    <div className="field">
                      <label>{appText("text_86a6123f76f8")}</label>
                      <input
                        type="date"
                        value={form.shared_camp_context.fight_date ?? ""}
                        onChange={(event) => setSharedField("fight_date", event.target.value)}
                      />
                    </div>
                    <div className="field">
                      <label>{appText("text_b026c8c436cc")}</label>
                      <select
                        value={form.shared_camp_context.weigh_in_type ?? ""}
                        onChange={(event) => setSharedField("weigh_in_type", event.target.value || null)}
                      >
                        <option value="">{appText("text_2a78025de6aa")}</option>
                        {WEIGH_IN_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>{translateUiText(appText, option.label)}</option>
                        ))}
                      </select>
                    </div>
                    <div className="field">
                      <label>{appText("text_d940e1045bec")}</label>
                      <input
                        type="time"
                        value={form.shared_camp_context.weigh_in_time ?? ""}
                        onChange={(event) => setSharedField("weigh_in_time", event.target.value)}
                      />
                    </div>
                    <div className="field">
                      <label>{appText("text_d9b276f147dc")}</label>
                      <select
                        value={form.shared_camp_context.current_weight_source ?? ""}
                        onChange={(event) => handleWeightSourceChange(event.target.value)}
                      >
                        {WEIGHT_SOURCE_OPTIONS.map((value) => (
                          <option key={value || "empty"} value={value}>{value || "Select"}</option>
                        ))}
                      </select>
                      <p className="muted">{appText("text_b31f0c9607bb")}</p>
                    </div>
                    <div className="field">
                      <label>{appText("text_78f0ccf55ef4")}</label>
                      <input
                        type="datetime-local"
                        value={form.shared_camp_context.current_weight_recorded_at ?? ""}
                        onChange={(event) => setSharedField("current_weight_recorded_at", event.target.value)}
                      />
                    </div>
                    <div className="field">
                      <label>{appText("text_b462980141b0")}</label>
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
                <p className="nutrition-group-label">{appText("text_477ce386a7c2")}</p>
                <article className="step-card nutrition-section">
                  <div className="form-section-header">
                    <p className="kicker">{appText("text_d53d98c17749")}</p>
                    <h2 className="form-section-title">{appText("text_c302af01c71a")}</h2>
                  </div>
                  <div className="form-grid">
                    <div className="field">
                      <label>{appText("text_effe0fc0491c")}</label>
                      <input
                        type="number"
                        min="1"
                        max="6"
                        inputMode="numeric"
                        value={form.shared_camp_context.weekly_training_frequency ?? ""}
                        onChange={(event) => setSharedField("weekly_training_frequency", toNumber(event.target.value))}
                      />
                    </div>
                    <div className="field">
                      <div className="level-field-header">
                        <label htmlFor="nutritionFatigueLevel">{appText("text_cf260a4f2c6e")}</label>
                        {form.shared_camp_context.fatigue_level ? (
                          <button
                            type="button"
                            className="level-slider-clear"
                            onClick={() => setSharedField("fatigue_level", null)}
                          >
                            {appText("text_83b12c2216ef")}</button>
                        ) : null}
                      </div>
                      <LevelSlider
                        id="nutritionFatigueLevel"
                        ariaLabel={appText("text_cf260a4f2c6e")}
                        value={(form.shared_camp_context.fatigue_level as LevelValue | null) ?? null}
                        onChange={(value) => setSharedField("fatigue_level", value)}
                      />
                    </div>
                    <div className="field">
                      <label>{appText("text_646543197fec")}</label>
                      <select
                        value={form.nutrition_readiness.sleep_quality ?? ""}
                        onChange={(event) => setSleepQuality(event.target.value || null)}
                      >
                        {SLEEP_OPTIONS.map((option) => (
                          <option key={option.value || "empty"} value={option.value}>{translateUiText(appText, option.label)}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div className="nutrition-daytype-grid">
                    {TRAINING_AVAILABILITY_OPTIONS.map((option) => (
                      <div key={option.value} className="field">
                        <label>{translateUiText(appText, option.label)} {appText("text_ca93e08b46db")}</label>
                        <select
                          value={form.shared_camp_context.session_types_by_day[option.value] ?? ""}
                          onChange={(event) => setDayType(option.value, event.target.value)}
                        >
                          <option value="">{appText("text_466c9d7bc6a7")}</option>
                          {DAY_TYPE_OPTIONS.map((dayTypeOption) => (
                            <option key={dayTypeOption.value} value={dayTypeOption.value}>{dayTypeOption.label}</option>
                          ))}
                        </select>
                      </div>
                    ))}
                  </div>
                  <p className="muted">{appText("text_b8e84b6d8949")}</p>
                </article>

                <article className="step-card nutrition-section">
                  <div className="form-section-header">
                    <p className="kicker">{appText("text_7ab78b7058dd")}</p>
                    <h2 className="form-section-title">{appText("text_d831da0f3e20")}</h2>
                  </div>
                  <div className="form-grid">
                    <div className="field">
                      <label>{appText("text_561d7c9e90be")}</label>
                      <select
                        value={form.nutrition_profile.daily_activity_level ?? ""}
                        onChange={(event) => setProfileField("daily_activity_level", event.target.value || null)}
                      >
                        <option value="">{appText("text_2a78025de6aa")}</option>
                        {ACTIVITY_OPTIONS.map((option) => (
                          <option key={option.value} value={option.value}>{translateUiText(appText, option.label)}</option>
                        ))}
                      </select>
                    </div>
                    <div className="field">
                      <label>{appText("text_e9ed443a4b55")}</label>
                      <input
                        value={toCsv(form.nutrition_profile.dietary_restrictions)}
                        onChange={(event) => setProfileField("dietary_restrictions", toList(event.target.value))}
                      />
                    </div>
                    <div className="field">
                      <label>{appText("text_daa3eadd18c1")}</label>
                      <input
                        type="number"
                        min="1"
                        max="8"
                        inputMode="numeric"
                        value={form.nutrition_profile.meals_per_day_preference ?? ""}
                        onChange={(event) => setProfileField("meals_per_day_preference", toNumber(event.target.value))}
                      />
                    </div>
                    <div className="field">
                      <label>{appText("text_0faeadc4eac9")}</label>
                      <select
                        value={form.nutrition_profile.caffeine_use == null ? "" : form.nutrition_profile.caffeine_use ? "yes" : "no"}
                        onChange={(event) => setProfileField("caffeine_use", event.target.value ? event.target.value === "yes" : null)}
                      >
                        <option value="">{appText("text_2a78025de6aa")}</option>
                        <option value="yes">{appText("text_85a39ab345d6")}</option>
                        <option value="no">{appText("text_1ea442a134b2")}</option>
                      </select>
                    </div>
                    <div className="field">
                      <label>{appText("text_2ce6523021b1")}</label>
                      <input
                        value={toCsv(form.nutrition_profile.supplement_use)}
                        onChange={(event) => setProfileField("supplement_use", toList(event.target.value))}
                      />
                    </div>
                  </div>
                  <p className="muted">{appText("text_be9b0338c46c")}</p>
                </article>
              </div>

            </div>

            <aside className="nutrition-side-column">
              <article className="support-panel">
                <p className="kicker">{appText("text_f38d9950af4f")}</p>
                <p className="muted">{workspace.derived.readiness_flags.length ? workspace.derived.readiness_flags.join(", ") : appText("text_ca7fcba73355")}</p>
              </article>
              <article className="support-panel">
                <p className="kicker">{appText("text_581d1b4da4c0")}</p>
                <p className="muted">{appText("text_6abc55f3ebc4")}</p>
                <Link href="/nutrition/bodyweight-log" className="ghost-button">{appText("text_99c115ccf9f4")}</Link>
              </article>
            </aside>
          </div>
        )}

        {message ? <div className="success-banner athlete-motion-slot athlete-motion-status">{message}</div> : null}
        {error ? <div className="error-banner athlete-motion-slot athlete-motion-status">{error}</div> : null}

        <div className="nutrition-sticky-save">
          <button type="button" className="cta" onClick={handleSave} disabled={isPending || !workspace}>
            {isPending ? appText("text_dc85af8f2b1d") : appText("text_4ce6dffa4a18")}
          </button>
        </div>
      </section>
    </RequireAuth>
  );
}
