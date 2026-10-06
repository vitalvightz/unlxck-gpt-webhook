"use client";

import { useRef, useState, type FormEvent } from "react";
import { submitInjuryEpisodeObservation } from "@/lib/api";
import type { AchillesProgressionAssessment, AchillesProgressionInput } from "@/lib/api-schema.generated";
import type { InjuryFlagRecord } from "@/lib/types";
import styles from "./achilles-assessment-form.module.css";

function YesNo({ name, label }: { name: string; label: string }) {
  return <label>{label}<select name={name} defaultValue="unknown">
    <option value="unknown">Not known / not assessed</option><option value="yes">Yes</option><option value="no">No</option>
  </select></label>;
}

function numeric(data: FormData, name: string) {
  const raw = String(data.get(name) ?? "").trim();
  if (!raw) return null;
  const value = Number(raw);
  if (!Number.isFinite(value) || value < 0) throw new Error("Use a non-negative number for recorded measurements.");
  return value;
}

function instant(data: FormData, name: string) {
  const raw = String(data.get(name) ?? "");
  if (!raw) return null;
  const date = new Date(raw);
  if (!Number.isFinite(date.getTime()) || date.getTime() > Date.now()) throw new Error("Use the actual observation time, at or before now.");
  return date.toISOString();
}

function choice<const T extends string>(data: FormData, name: string, allowed: readonly T[]): T {
  const value = String(data.get(name) ?? allowed[0]);
  if (!allowed.includes(value as T)) throw new Error("Select a recorded answer or leave it unknown.");
  return value as T;
}

function boolean(data: FormData, name: string) {
  const value = choice(data, name, ["unknown", "yes", "no"]);
  return value === "unknown" ? null : value === "yes";
}

export function AchillesAssessmentForm({ injury, token, onRefresh, disabled = false }: {
  injury: InjuryFlagRecord; token: string; onRefresh: () => Promise<void>; disabled?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const pending = useRef<{ key: string; id: string } | null>(null);
  const review = injury.rehab_decision?.achilles_load_review;
  if (!review || !injury.episode_id || !["open", "monitoring"].includes(injury.status)) return null;
  if (!injury.side || injury.side === "unknown") return <p className="today-field-hint">Confirm the Achilles side in your injury details before recording an assessment.</p>;

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || disabled) return;
    const data = new FormData(event.currentTarget);
    setError(""); setMessage(""); setBusy(true);
    let saved = false;
    try {
      const assessedAt = instant(data, "assessed_at");
      if (!assessedAt) throw new Error("Add the actual assessment time.");
      const heel = boolean(data, "heel_rise_completed");
      const range = boolean(data, "range_assessed");
      const loadingAt = instant(data, "loading_performed_at");
      const delayedAt = instant(data, "delayed_response_at");
      const during = numeric(data, "during_symptoms");
      const delayed = numeric(data, "delayed_symptoms");
      if ((during !== null && during > 10) || (delayed !== null && delayed > 10)) throw new Error("Symptom ratings use a 0–10 scale.");
      if ((during !== null && !loadingAt) || (delayed !== null && !delayedAt)) throw new Error("Add the observation time for each symptom rating.");
      if (delayedAt && (!loadingAt || delayedAt <= loadingAt)) throw new Error("The delayed response must follow the recorded loading.");
      if (loadingAt && loadingAt > assessedAt) throw new Error("Loading must occur at or before the assessment.");
      const reps = numeric(data, "heel_rise_repetitions");
      if (reps !== null && !Number.isInteger(reps)) throw new Error("Repetitions must be a whole number.");
      if (heel !== true && (reps !== null || boolean(data, "heel_rise_assessor_usable") !== null
          || String(data.get("heel_rise_mode")) !== "unknown" || String(data.get("heel_rise_quality")) !== "unknown")) {
        throw new Error("Heel-rise results need a completed assessment, including an assessment that found you unable to do the movement.");
      }
      if (range !== true && (numeric(data, "resistance_kg") !== null || boolean(data, "range_load_assessor_usable") !== null
          || ["permitted_range", "resistance", "range_load_tolerance"].some(name => String(data.get(name)) !== "unknown"))) {
        throw new Error("Range and load results need an actual assessment. Leave unassessed results unknown.");
      }
      const assessor = choice(data, "assessor", ["unknown", "self_reported", "coach_observed", "clinician_physio"]);
      const pathology = choice(data, "incompatible_pathology", ["not_assessed", "unknown", "suspected", "excluded"]);
      if (pathology === "excluded" && assessor !== "clinician_physio") throw new Error("Only record pathology exclusion reported by a clinician or physio; otherwise leave it not assessed.");
      const resistance = range === true ? choice(data, "resistance", ["unknown", "bodyweight", "external"]) : "unknown";
      const payload: AchillesProgressionInput = {
        site: choice(data, "site", ["unknown", "midportion", "insertional"]), incompatible_pathology: pathology,
        suspected_rupture: boolean(data, "suspected_rupture"), marked_weakness: boolean(data, "marked_weakness"),
        traumatic_loss_of_function: boolean(data, "traumatic_loss_of_function"), clinician_restriction: boolean(data, "clinician_restriction"),
        heel_rise_completed: heel,
        heel_rise_mode: heel === true ? choice(data, "heel_rise_mode", ["unknown", "double_leg", "single_leg"]) : "unknown",
        heel_rise_quality: heel === true ? choice(data, "heel_rise_quality", ["unknown", "controlled", "reduced_control", "unable"]) : "unknown",
        heel_rise_repetitions: heel === true ? reps : null,
        heel_rise_assessor_usable: heel === true ? boolean(data, "heel_rise_assessor_usable") : null,
        loading_task: choice(data, "loading_task", ["unknown", "heel_rise_assessment", "clinician_selected"]),
        loading_performed_at: loadingAt, during_symptoms: during, delayed_symptoms: delayed, delayed_response_at: delayedAt,
        range_assessed: range, permitted_range: range === true ? choice(data, "permitted_range", ["unknown", "floor_level", "clinician_limited"]) : "unknown",
        resistance, resistance_kg: resistance === "external" ? numeric(data, "resistance_kg") : null,
        range_load_tolerance: range === true ? choice(data, "range_load_tolerance", ["unknown", "tolerated", "not_tolerated"]) : "unknown",
        range_load_assessor_usable: range === true ? boolean(data, "range_load_assessor_usable") : null,
      };
      const assessment: AchillesProgressionAssessment = { assessment_kind: "achilles_tendon_progression_v1", schema_version: 1,
        protocol_version: 1, side: injury.side!, assessed_at: assessedAt, assessor, payload };
      const key = JSON.stringify({ episode: injury.episode_id, assessment });
      if (pending.current?.key !== key) pending.current = { key, id: crypto.randomUUID() };
      await submitInjuryEpisodeObservation(token, { injury_id: injury.id, injury_episode_id: injury.episode_id!,
        event_type: "rehab_progression_assessment", report_id: pending.current.id, assessment });
      saved = true; pending.current = null;
      setMessage("Assessment report saved. LOAD remains closed.");
      await onRefresh();
    } catch (e) {
      setError(saved ? "Your report was saved, but Today could not refresh. Refresh the page to see the updated guidance."
        : e instanceof Error ? e.message : "Could not save the assessment report.");
    } finally { setBusy(false); }
  }

  return <details className={styles.panel}>
    <summary>Record Achilles assessment</summary>
    <p>Record an assessment that already happened. Do not perform a new test for this form. Follow your clinician&apos;s restrictions.</p>
    <p>LOAD remains closed. These are your reported observations, including any clinician or coach advice you report; assessor identity is not verified here.</p>
    <p>Each save replaces the earlier assessment snapshot for this episode. Include all known answers again when adding a delayed response. Leave unassessed answers unknown.</p>
    <form onSubmit={save}>
      <fieldset disabled={busy || disabled} className={styles.fields}>
        <legend>1. Assessment context — {injury.side} Achilles</legend>
        <label>Assessment time (your local time)<input type="datetime-local" name="assessed_at" required /></label>
        <label>Who assessed the movement, range and load?<select name="assessor" defaultValue="unknown">
          <option value="unknown">Not known / not assessed</option><option value="self_reported">My own observations</option>
          <option value="coach_observed">Observed by my coach</option><option value="clinician_physio">Assessed by my clinician / physio (reported by me)</option>
        </select></label>
        <label>Reported tendon site<select name="site" defaultValue="unknown"><option value="unknown">Not known</option>
          <option value="midportion">Midportion</option><option value="insertional">Insertional / at the heel attachment</option></select></label>
        <label>Other pathology assessed?<select name="incompatible_pathology" defaultValue="not_assessed">
          <option value="not_assessed">Not assessed</option><option value="unknown">Not known</option>
          <option value="suspected">Other pathology suspected</option><option value="excluded">Clinician / physio reported it excluded</option></select></label>
        <YesNo name="suspected_rupture" label="Suspected Achilles rupture?" />
        <YesNo name="marked_weakness" label="Marked weakness?" />
        <YesNo name="traumatic_loss_of_function" label="Loss of function after trauma?" />
        <YesNo name="clinician_restriction" label="Current clinician restriction on loading?" />
        <p className={styles.full}>A suspected rupture, sudden traumatic loss of function or another safety concern needs medical assessment before training.</p>
      </fieldset>
      <fieldset disabled={busy || disabled} className={styles.fields}>
        <legend>2. Existing heel-rise observation</legend>
        <YesNo name="heel_rise_completed" label="Was a heel-rise assessment completed?" />
        <label>Observed mode<select name="heel_rise_mode" defaultValue="unknown"><option value="unknown">Not known</option><option value="double_leg">Both legs</option><option value="single_leg">Single leg</option></select></label>
        <label>Observed movement quality<select name="heel_rise_quality" defaultValue="unknown"><option value="unknown">Not known</option><option value="controlled">Controlled</option><option value="reduced_control">Reduced control</option><option value="unable">Unable</option></select></label>
        <label>Recorded repetitions (optional)<input name="heel_rise_repetitions" type="number" min="0" step="1" /></label>
        <YesNo name="heel_rise_assessor_usable" label="Did the assessor say this observation was usable?" />
      </fieldset>
      <fieldset disabled={busy || disabled} className={styles.fields}>
        <legend>3. Actual loading and symptom response</legend>
        <label>Recorded loading task<select name="loading_task" defaultValue="unknown"><option value="unknown">Not known / not performed</option><option value="heel_rise_assessment">Heel-rise assessment</option><option value="clinician_selected">Clinician-selected task</option></select></label>
        <label>Loading time (your local time)<input name="loading_performed_at" type="datetime-local" /></label>
        <label>Symptoms during loading (0–10)<input name="during_symptoms" type="number" min="0" max="10" step="any" /></label>
        <label>Delayed symptoms (0–10, if observed)<input name="delayed_symptoms" type="number" min="0" max="10" step="any" /></label>
        <label>Delayed observation time (your local time)<input name="delayed_response_at" type="datetime-local" /></label>
        <p className={styles.full}>These ratings record symptoms. No number here means you are ready for LOAD.</p>
      </fieldset>
      <fieldset disabled={busy || disabled} className={styles.fields}>
        <legend>4. Assessed range and load</legend>
        <p className={styles.full}>Record clinician / physio advice only if it was actually given. Missing clinical advice remains unavailable.</p>
        <YesNo name="range_assessed" label="Was range and load assessed?" />
        <label>Reported permitted range<select name="permitted_range" defaultValue="unknown"><option value="unknown">Not known</option><option value="floor_level">Floor level</option><option value="clinician_limited">Individually limited by clinician</option></select></label>
        <label>Assessed resistance<select name="resistance" defaultValue="unknown"><option value="unknown">Not known</option><option value="bodyweight">Bodyweight</option><option value="external">External resistance</option></select></label>
        <label>Measured external resistance (kg, optional)<input name="resistance_kg" type="number" min="0" step="any" /></label>
        <label>Reported tolerance<select name="range_load_tolerance" defaultValue="unknown"><option value="unknown">Not known</option><option value="tolerated">Tolerated</option><option value="not_tolerated">Not tolerated</option></select></label>
        <YesNo name="range_load_assessor_usable" label="Did the assessor say this range/load observation was usable?" />
      </fieldset>
      <button className="today-segment" type="submit" disabled={busy || disabled}>{busy ? "Saving…" : "Save assessment report"}</button>
      {message ? <p role="status">{message}</p> : null}
      {error ? <p role="alert">{error}</p> : null}
    </form>
  </details>;
}
