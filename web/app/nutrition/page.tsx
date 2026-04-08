"use client";

import Link from "next/link";
import { useEffect, useState, useTransition } from "react";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { getNutritionCurrent, updateNutritionCurrent } from "@/lib/api";
import { TRAINING_AVAILABILITY_OPTIONS, toggleListValue } from "@/lib/intake-options";
import type {
  NutritionBodyweightLogEntry,
  NutritionProfileInput,
  NutritionWorkspaceState,
  NutritionWorkspaceUpdateRequest,
  SessionDayType,
} from "@/lib/types";

const SEX_OPTIONS = [
  { value: "male", label: "Male" },
  { value: "female", label: "Female" },
];
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
const PHASE_OPTIONS = ["", "GPP", "SPP", "TAPER"];
const FATIGUE_OPTIONS = ["", "low", "moderate", "high"];
const SLEEP_OPTIONS = ["", "good", "mixed", "poor"];
const APPETITE_OPTIONS = ["", "normal", "low", "high"];
const WEIGHT_SOURCE_OPTIONS = ["", "manual", "latest_bodyweight_log", "imported"];
const RESTRICTION_OPTIONS = ["", "none", "minor", "moderate", "major"];
const DAY_TYPE_OPTIONS: Array<{ value: SessionDayType; label: string }> = [
  { value: "hard_spar", label: "Hard spar" },
  { value: "technical", label: "Technical" },
  { value: "strength", label: "Strength" },
  { value: "conditioning", label: "Conditioning" },
  { value: "recovery", label: "Recovery" },
  { value: "off", label: "Off" },
];

function toNumber(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function toList(value: string): string[] {
  return value.split(",").map((entry) => entry.trim()).filter(Boolean);
}

function toCsv(values: string[]): string {
  return values.join(", ");
}

function localDateTimeValue(): string {
  const now = new Date();
  const adjusted = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return adjusted.toISOString().slice(0, 16);
}

function defaultNutritionProfile(existing?: NutritionProfileInput): NutritionProfileInput {
  return {
    sex: existing?.sex ?? null,
    age: existing?.age ?? null,
    height_cm: existing?.height_cm ?? null,
    daily_activity_level: existing?.daily_activity_level ?? null,
    dietary_restrictions: existing?.dietary_restrictions ?? [],
    food_preferences: existing?.food_preferences ?? [],
    meals_per_day_preference: existing?.meals_per_day_preference ?? null,
    foods_avoided_pre_session: existing?.foods_avoided_pre_session ?? [],
    foods_avoided_fight_week: existing?.foods_avoided_fight_week ?? [],
    supplement_use: existing?.supplement_use ?? [],
    caffeine_use: existing?.caffeine_use ?? null,
  };
}

function emptyUpdateRequest(profile?: NutritionProfileInput): NutritionWorkspaceUpdateRequest {
  return {
    nutrition_profile: defaultNutritionProfile(profile),
    shared_camp_context: {
      fight_date: "",
      rounds_format: "3 x 3",
      weigh_in_type: null,
      weigh_in_time: "",
      current_weight_kg: null,
      current_weight_recorded_at: "",
      current_weight_source: null,
      target_weight_kg: null,
      target_weight_range_kg: null,
      phase_override: null,
      fatigue_level: "moderate",
      weekly_training_frequency: null,
      training_availability: [],
      hard_sparring_days: [],
      technical_skill_days: [],
      session_types_by_day: {},
      injuries: "",
      guided_injury: null,
      training_restriction_level: null,
    },
    s_and_c_preferences: {
      equipment_access: [],
      key_goals: [],
      weak_areas: [],
      training_preference: "",
      mindset_challenges: "",
      notes: "",
      random_seed: null,
    },
    nutrition_readiness: { sleep_quality: null, appetite_status: null },
    nutrition_monitoring: { daily_bodyweight_log: [] },
    nutrition_coach_controls: {
      coach_override_enabled: false,
      athlete_override_enabled: false,
      do_not_reduce_below_calories: null,
      protein_floor_g_per_kg: null,
      fight_week_manual_mode: false,
      water_cut_locked_to_manual: false,
    },
  };
}

function toUpdateRequest(workspace: NutritionWorkspaceState): NutritionWorkspaceUpdateRequest {
  return {
    nutrition_profile: defaultNutritionProfile(workspace.nutrition_profile),
    shared_camp_context: {
      ...workspace.shared_camp_context,
      fight_date: workspace.shared_camp_context.fight_date ?? "",
      rounds_format: workspace.shared_camp_context.rounds_format ?? "3 x 3",
      weigh_in_time: workspace.shared_camp_context.weigh_in_time ?? "",
      current_weight_recorded_at: workspace.shared_camp_context.current_weight_recorded_at ?? "",
      injuries: workspace.shared_camp_context.injuries ?? "",
    },
    s_and_c_preferences: workspace.s_and_c_preferences,
    nutrition_readiness: workspace.nutrition_readiness,
    nutrition_monitoring: workspace.nutrition_monitoring,
    nutrition_coach_controls: workspace.nutrition_coach_controls,
  };
}

function StatusRows({ workspace }: { workspace: NutritionWorkspaceState }) {
  const derived = workspace.derived;
  return (
    <div className="review-detail-list nutrition-review-list">
      {[
        ["Days until fight", derived.days_until_fight != null ? String(derived.days_until_fight) : "Not set"],
        ["Current phase", derived.current_phase_effective || "Not derived yet"],
        ["Cut size", `${derived.weight_cut_pct.toFixed(1)}%`],
        ["Fight week override", derived.fight_week_override_band.replaceAll("_", " ")],
      ].map(([label, value]) => (
        <div key={label} className="review-detail-row">
          <p className="review-detail-label">{label}</p>
          <p className="review-detail-value">{value}</p>
        </div>
      ))}
    </div>
  );
}

export default function NutritionPage() {
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
        setForm(toUpdateRequest(nextWorkspace));
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

  function setReadinessField(key: "sleep_quality" | "appetite_status", value: string | null) {
    setForm((current) => ({
      ...current,
      nutrition_readiness: {
        ...current.nutrition_readiness,
        [key]: value as NutritionWorkspaceUpdateRequest["nutrition_readiness"][typeof key],
      },
    }));
  }

  function toggleDayList(key: "training_availability" | "hard_sparring_days" | "technical_skill_days", day: string) {
    setForm((current) => ({
      ...current,
      shared_camp_context: {
        ...current.shared_camp_context,
        [key]: toggleListValue(current.shared_camp_context[key], day),
      },
    }));
  }

  function setDayType(day: string, value: string) {
    setForm((current) => {
      const next = { ...current.shared_camp_context.session_types_by_day };
      if (!value) delete next[day];
      else next[day] = value as SessionDayType;
      return { ...current, shared_camp_context: { ...current.shared_camp_context, session_types_by_day: next } };
    });
  }

  function setLog(index: number, key: keyof NutritionBodyweightLogEntry, value: unknown) {
    setForm((current) => ({
      ...current,
      nutrition_monitoring: {
        ...current.nutrition_monitoring,
        daily_bodyweight_log: current.nutrition_monitoring.daily_bodyweight_log.map((entry, entryIndex) =>
          entryIndex === index ? { ...entry, [key]: value } : entry,
        ),
      },
    }));
  }

  function addLog() {
    setForm((current) => ({
      ...current,
      nutrition_monitoring: {
        ...current.nutrition_monitoring,
        daily_bodyweight_log: [
          ...current.nutrition_monitoring.daily_bodyweight_log,
          { date: "", weight_kg: 0, time: "", is_fasted: null, notes: "" },
        ],
      },
    }));
  }

  function removeLog(index: number) {
    setForm((current) => ({
      ...current,
      nutrition_monitoring: {
        ...current.nutrition_monitoring,
        daily_bodyweight_log: current.nutrition_monitoring.daily_bodyweight_log.filter((_, entryIndex) => entryIndex !== index),
      },
    }));
  }

  function handleSave() {
    if (!session?.access_token) return;
    setError(null);
    setMessage(null);
    startTransition(async () => {
      try {
        const nextWorkspace = await updateNutritionCurrent(session.access_token, form);
        setWorkspace(nextWorkspace);
        setForm(toUpdateRequest(nextWorkspace));
        await refreshMe();
        setMessage("Nutrition workspace saved.");
      } catch (saveError) {
        setError(saveError instanceof Error ? saveError.message : "Unable to save nutrition workspace.");
      }
    });
  }

  return (
    <RequireAuth>
      <section className="panel">
        <div className="section-heading">
          <div className="athlete-motion-slot athlete-motion-header">
            <p className="kicker">Nutrition &amp; Weight</p>
            <h1>Weight setup, monitoring, and readiness</h1>
            <p className="muted">This page keeps the nutrition foundation in one place while onboarding still drives generation.</p>
          </div>
          <div className="status-card athlete-motion-slot athlete-motion-status">
            <p className="status-label">Athlete</p>
            <h2 className="plan-summary-title">{me?.profile.full_name || me?.profile.email || "Nutrition workspace"}</h2>
            <div className="plan-summary-actions nutrition-inline-actions">
              <Link href="/onboarding" className="ghost-button">Onboarding</Link>
              <Link href="/settings" className="ghost-button">Settings</Link>
            </div>
          </div>
        </div>

        {!workspace ? (
          <section className="support-panel loading-card"><p className="muted">Loading nutrition workspace.</p></section>
        ) : (
          <div className="nutrition-page-grid">
            <div className="nutrition-main-column">
              <article className="step-card nutrition-section">
                <div className="form-section-header"><p className="kicker">Summary</p><h2 className="form-section-title">Derived status</h2></div>
                <StatusRows workspace={workspace} />
                <p className="muted">Foundation status: <strong>{workspace.derived.foundation_status}</strong>{workspace.derived.missing_required_fields.length ? ` · Missing: ${workspace.derived.missing_required_fields.join(", ")}` : ""}</p>
              </article>

              <article className="step-card nutrition-section">
                <div className="form-section-header"><p className="kicker">Athlete basics</p><h2 className="form-section-title">Stable physiology</h2></div>
                <div className="form-grid">
                  <div className="field"><label>Sex</label><select value={form.nutrition_profile.sex ?? ""} onChange={(event) => setProfileField("sex", event.target.value || null)}><option value="">Select</option>{SEX_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div>
                  <div className="field"><label>Age</label><input type="number" value={form.nutrition_profile.age ?? ""} onChange={(event) => setProfileField("age", toNumber(event.target.value))} /></div>
                  <div className="field"><label>Height (cm)</label><input type="number" value={form.nutrition_profile.height_cm ?? ""} onChange={(event) => setProfileField("height_cm", toNumber(event.target.value))} /></div>
                  <div className="field"><label>Daily activity</label><select value={form.nutrition_profile.daily_activity_level ?? ""} onChange={(event) => setProfileField("daily_activity_level", event.target.value || null)}><option value="">Select</option>{ACTIVITY_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div>
                </div>
              </article>

              <article className="step-card nutrition-section">
                <div className="form-section-header"><p className="kicker">Fight weight setup</p><h2 className="form-section-title">Weight, target, and timing</h2></div>
                <div className="form-grid">
                  <div className="field"><label>Current weight (kg)</label><input type="number" step="0.1" value={form.shared_camp_context.current_weight_kg ?? ""} onChange={(event) => { const nextValue = toNumber(event.target.value); setSharedField("current_weight_kg", nextValue); if (nextValue != null && !form.shared_camp_context.current_weight_source) { setSharedField("current_weight_source", "manual"); if (!form.shared_camp_context.current_weight_recorded_at) setSharedField("current_weight_recorded_at", localDateTimeValue()); } }} /></div>
                  <div className="field"><label>Current weight source</label><select value={form.shared_camp_context.current_weight_source ?? ""} onChange={(event) => setSharedField("current_weight_source", event.target.value || null)}>{WEIGHT_SOURCE_OPTIONS.map((value) => <option key={value} value={value}>{value || "Select"}</option>)}</select></div>
                  <div className="field"><label>Weight recorded at</label><input type="datetime-local" value={form.shared_camp_context.current_weight_recorded_at ?? ""} onChange={(event) => setSharedField("current_weight_recorded_at", event.target.value)} /></div>
                  <div className="field"><label>Target weight (kg)</label><input type="number" step="0.1" value={form.shared_camp_context.target_weight_kg ?? ""} onChange={(event) => setSharedField("target_weight_kg", toNumber(event.target.value))} /></div>
                  <div className="field"><label>Target range lower (kg)</label><input type="number" step="0.1" value={(form.shared_camp_context.target_weight_range_kg?.[0] ?? "") as number | string} onChange={(event) => { const lower = toNumber(event.target.value); const upper = form.shared_camp_context.target_weight_range_kg?.[1] ?? null; setSharedField("target_weight_range_kg", lower != null && upper != null ? [lower, upper] : null); }} /></div>
                  <div className="field"><label>Target range upper (kg)</label><input type="number" step="0.1" value={(form.shared_camp_context.target_weight_range_kg?.[1] ?? "") as number | string} onChange={(event) => { const lower = form.shared_camp_context.target_weight_range_kg?.[0] ?? null; const upper = toNumber(event.target.value); setSharedField("target_weight_range_kg", lower != null && upper != null ? [lower, upper] : null); }} /></div>
                  <div className="field"><label>Fight date</label><input type="date" value={form.shared_camp_context.fight_date ?? ""} onChange={(event) => setSharedField("fight_date", event.target.value)} /></div>
                  <div className="field"><label>Weigh-in type</label><select value={form.shared_camp_context.weigh_in_type ?? ""} onChange={(event) => setSharedField("weigh_in_type", event.target.value || null)}><option value="">Select</option>{WEIGH_IN_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div>
                  <div className="field"><label>Weigh-in time</label><input type="time" value={form.shared_camp_context.weigh_in_time ?? ""} onChange={(event) => setSharedField("weigh_in_time", event.target.value)} /></div>
                  <div className="field"><label>Rounds format</label><input value={form.shared_camp_context.rounds_format ?? ""} onChange={(event) => setSharedField("rounds_format", event.target.value)} /></div>
                  <div className="field"><label>Phase override</label><select value={form.shared_camp_context.phase_override ?? ""} onChange={(event) => setSharedField("phase_override", event.target.value || null)}>{PHASE_OPTIONS.map((value) => <option key={value || "empty"} value={value}>{value || "Auto"}</option>)}</select></div>
                </div>
              </article>

              <article className="step-card nutrition-section">
                <div className="form-section-header"><p className="kicker">Training pattern</p><h2 className="form-section-title">Schedule and fatigue</h2></div>
                <div className="form-grid">
                  <div className="field"><label>Sessions per week</label><input type="number" min="1" max="6" value={form.shared_camp_context.weekly_training_frequency ?? ""} onChange={(event) => setSharedField("weekly_training_frequency", toNumber(event.target.value))} /></div>
                  <div className="field"><label>Fatigue level</label><select value={form.shared_camp_context.fatigue_level ?? ""} onChange={(event) => setSharedField("fatigue_level", event.target.value || null)}>{FATIGUE_OPTIONS.map((value) => <option key={value || "empty"} value={value}>{value || "Select"}</option>)}</select></div>
                  <div className="field"><label>Sleep quality</label><select value={form.nutrition_readiness.sleep_quality ?? ""} onChange={(event) => setReadinessField("sleep_quality", event.target.value || null)}>{SLEEP_OPTIONS.map((value) => <option key={value || "empty"} value={value}>{value || "Select"}</option>)}</select></div>
                  <div className="field"><label>Appetite status</label><select value={form.nutrition_readiness.appetite_status ?? ""} onChange={(event) => setReadinessField("appetite_status", event.target.value || null)}>{APPETITE_OPTIONS.map((value) => <option key={value || "empty"} value={value}>{value || "Select"}</option>)}</select></div>
                  <div className="field"><label>Restriction level</label><select value={form.shared_camp_context.training_restriction_level ?? ""} onChange={(event) => setSharedField("training_restriction_level", event.target.value || null)}>{RESTRICTION_OPTIONS.map((value) => <option key={value || "empty"} value={value}>{value || "Select"}</option>)}</select></div>
                </div>
                <div className="field"><label>Training availability</label><div className="checkbox-grid">{TRAINING_AVAILABILITY_OPTIONS.map((option) => <label key={option.value} className={`checkbox-card ${form.shared_camp_context.training_availability.includes(option.value) ? "checkbox-card-checked" : ""}`.trim()}><input type="checkbox" checked={form.shared_camp_context.training_availability.includes(option.value)} onChange={() => toggleDayList("training_availability", option.value)} /><span className="checkbox-card-copy"><span className="checkbox-card-title">{option.label}</span></span></label>)}</div></div>
                <div className="field"><label>Hard sparring days</label><div className="checkbox-grid">{TRAINING_AVAILABILITY_OPTIONS.map((option) => <label key={option.value} className={`checkbox-card ${form.shared_camp_context.hard_sparring_days.includes(option.value) ? "checkbox-card-checked" : ""}`.trim()}><input type="checkbox" checked={form.shared_camp_context.hard_sparring_days.includes(option.value)} onChange={() => toggleDayList("hard_sparring_days", option.value)} /><span className="checkbox-card-copy"><span className="checkbox-card-title">{option.label}</span></span></label>)}</div></div>
                <div className="field"><label>Technical / lighter skill days</label><div className="checkbox-grid">{TRAINING_AVAILABILITY_OPTIONS.map((option) => <label key={option.value} className={`checkbox-card ${form.shared_camp_context.technical_skill_days.includes(option.value) ? "checkbox-card-checked" : ""}`.trim()}><input type="checkbox" checked={form.shared_camp_context.technical_skill_days.includes(option.value)} onChange={() => toggleDayList("technical_skill_days", option.value)} /><span className="checkbox-card-copy"><span className="checkbox-card-title">{option.label}</span></span></label>)}</div></div>
                {form.shared_camp_context.training_availability.length ? <div className="nutrition-daytype-grid">{form.shared_camp_context.training_availability.map((day) => <div key={day} className="field"><label>{TRAINING_AVAILABILITY_OPTIONS.find((option) => option.value === day)?.label ?? day} day type</label><select value={form.shared_camp_context.session_types_by_day[day] ?? ""} onChange={(event) => setDayType(day, event.target.value)}><option value="">Optional label</option>{DAY_TYPE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div>)}</div> : null}
                <div className="field"><label>Injuries / restrictions</label><textarea value={form.shared_camp_context.injuries ?? ""} onChange={(event) => setSharedField("injuries", event.target.value)} /></div>
              </article>

              <article className="step-card nutrition-section">
                <div className="form-section-header"><p className="kicker">Nutrition defaults</p><h2 className="form-section-title">Preferences and adherence</h2></div>
                <div className="form-grid">
                  <div className="field"><label>Dietary restrictions</label><input value={toCsv(form.nutrition_profile.dietary_restrictions)} onChange={(event) => setProfileField("dietary_restrictions", toList(event.target.value))} /></div>
                  <div className="field"><label>Food preferences</label><input value={toCsv(form.nutrition_profile.food_preferences)} onChange={(event) => setProfileField("food_preferences", toList(event.target.value))} /></div>
                  <div className="field"><label>Meals per day</label><input type="number" min="1" max="8" value={form.nutrition_profile.meals_per_day_preference ?? ""} onChange={(event) => setProfileField("meals_per_day_preference", toNumber(event.target.value))} /></div>
                  <div className="field"><label>Caffeine use</label><select value={form.nutrition_profile.caffeine_use == null ? "" : form.nutrition_profile.caffeine_use ? "yes" : "no"} onChange={(event) => setProfileField("caffeine_use", event.target.value ? event.target.value === "yes" : null)}><option value="">Select</option><option value="yes">Yes</option><option value="no">No</option></select></div>
                  <div className="field"><label>Supplements</label><input value={toCsv(form.nutrition_profile.supplement_use)} onChange={(event) => setProfileField("supplement_use", toList(event.target.value))} /></div>
                  <div className="field"><label>Foods avoided pre-session</label><input value={toCsv(form.nutrition_profile.foods_avoided_pre_session)} onChange={(event) => setProfileField("foods_avoided_pre_session", toList(event.target.value))} /></div>
                  <div className="field"><label>Foods avoided fight week</label><input value={toCsv(form.nutrition_profile.foods_avoided_fight_week)} onChange={(event) => setProfileField("foods_avoided_fight_week", toList(event.target.value))} /></div>
                </div>
              </article>

              <article className="step-card nutrition-section">
                <div className="form-section-header"><p className="kicker">Monitoring</p><h2 className="form-section-title">Daily bodyweight log</h2></div>
                <div className="nutrition-log-list">{form.nutrition_monitoring.daily_bodyweight_log.map((entry, index) => <div key={`log-${index + 1}`} className="nutrition-log-row"><div className="field"><label>Date</label><input type="date" value={entry.date} onChange={(event) => setLog(index, "date", event.target.value)} /></div><div className="field"><label>Weight (kg)</label><input type="number" step="0.1" value={entry.weight_kg || ""} onChange={(event) => setLog(index, "weight_kg", toNumber(event.target.value) ?? 0)} /></div><div className="field"><label>Time</label><input type="time" value={entry.time ?? ""} onChange={(event) => setLog(index, "time", event.target.value)} /></div><div className="field"><label>Notes</label><input value={entry.notes ?? ""} onChange={(event) => setLog(index, "notes", event.target.value)} /></div><button type="button" className="ghost-button" onClick={() => removeLog(index)}>Remove</button></div>)}</div>
                <div className="plan-summary-actions"><button type="button" className="ghost-button" onClick={addLog}>Add weigh-in</button></div>
              </article>
            </div>

            <aside className="nutrition-side-column">
              <article className="support-panel"><p className="kicker">Readiness flags</p><p className="muted">{workspace.derived.readiness_flags.join(", ")}</p></article>
              <article className="support-panel"><p className="kicker">Planner link</p><p className="muted">Availability, fatigue, injuries, and fight timing still flow into the main planner. This page just gives those nutrition-specific data points a proper home.</p></article>
            </aside>
          </div>
        )}

        {message ? <div className="success-banner athlete-motion-slot athlete-motion-status">{message}</div> : null}
        {error ? <div className="error-banner athlete-motion-slot athlete-motion-status">{error}</div> : null}

        <div className="form-actions athlete-motion-slot athlete-motion-rail">
          <button type="button" className="cta" onClick={handleSave} disabled={isPending || !workspace}>{isPending ? "Saving..." : "Save nutrition workspace"}</button>
        </div>
      </section>
    </RequireAuth>
  );
}
