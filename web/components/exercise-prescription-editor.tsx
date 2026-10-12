"use client";

import { useState } from "react";
import type { ExerciseChangeDose } from "@/lib/types";
import { finishedDose, validDose, type DoseDraft } from "@/lib/exercise-dose";
import styles from "./exercise-customisation.module.css";

function TimeField({ label, value, onChange, rest = false }: {
  label: string; value?: number | null; onChange: (value: number | null) => void; rest?: boolean;
}) {
  const [unit, setUnit] = useState(!rest && value && value >= 60 && value % 60 === 0 ? 60 : 1);
  return <label className={styles.doseField}><span>{label}</span><div className={styles.unitField}>
    <input aria-label={label} type="number" inputMode="decimal" min={rest ? 0 : 1 / unit}
      max={(rest ? 3600 : 36000) / unit} step="any" value={value == null ? "" : value / unit}
      onChange={e => onChange(e.target.value === "" ? null : Math.round(Number(e.target.value) * unit))} />
    <select aria-label={`${label} unit`} value={unit} onChange={e => setUnit(Number(e.target.value))}>
      <option value={1}>sec</option><option value={60}>min</option>
    </select>
  </div></label>;
}

/** The same prescription editor for Add, Swap and an existing rendered card. */
export function ExercisePrescriptionEditor({ initial, action, busy, cues, stopRules, onSubmit }: {
  initial: DoseDraft; action: string; busy: boolean; cues?: string[]; stopRules?: string[];
  onSubmit: (dose: ExerciseChangeDose, cues?: string[], stopRules?: string[]) => void;
}) {
  const [dose, setDose] = useState(initial);
  const [cueText, setCueText] = useState((cues ?? []).join("\n"));
  const [stopText, setStopText] = useState((stopRules ?? []).join("\n"));
  const coaching = cues !== undefined || stopRules !== undefined;
  const update = (field: keyof DoseDraft, value: DoseDraft[keyof DoseDraft]) => setDose(current => ({ ...current, [field]: value }));
  function number(field: "sets" | "reps" | "rounds" | "rpe", label: string, max: number, optional = false) {
    return <label className={styles.doseField}><span>{label}</span><input aria-label={label}
      type="number" inputMode="decimal" min={1} max={max} step={field === "rpe" ? 0.5 : 1}
      required={!optional} value={dose[field] ?? ""}
      onChange={e => update(field, e.target.value === "" ? null : Number(e.target.value))} /></label>;
  }
  return <form className={styles.prescriptionEditor} onSubmit={e => {
    e.preventDefault();
    if (validDose(dose)) onSubmit(finishedDose(dose), coaching ? cueText.split("\n").filter(s => s.trim()) : undefined,
      coaching ? stopText.split("\n").filter(s => s.trim()) : undefined);
  }}>
    <label className={styles.formatField}><span className="sr-only">Dose format</span>
      <select aria-label="Dose format" value={dose.mode} onChange={e => setDose({
        mode: e.target.value as DoseDraft["mode"], rest_seconds: dose.rest_seconds,
        load_or_intensity: dose.load_or_intensity, rpe: dose.rpe, distance_unit: "m",
      })}>
        <option value="reps">Sets × reps</option><option value="duration">Time / hold</option>
        <option value="intervals">Intervals / rounds</option><option value="distance">Distance</option>
        <option value="text">Drill instructions</option>
      </select>
    </label>
    <div className={styles.doseGrid}>
      {dose.mode === "reps" ? <>{number("sets", "Sets", 100)}{number("reps", "Reps", 1000)}</>
        : dose.mode === "intervals" ? <>{number("rounds", "Rounds", 100)}<TimeField label="Work" value={dose.work_seconds} onChange={v => update("work_seconds", v)} /></>
        : dose.mode === "duration" ? <><TimeField label="Duration" value={dose.duration_seconds} onChange={v => update("duration_seconds", v)} />{number("sets", "Sets (optional)", 100, true)}</>
        : dose.mode === "distance" ? <><label className={styles.doseField}><span>Distance</span><div className={styles.unitField}>
          <input aria-label="Distance" type="number" inputMode="decimal" min={0.001} max={100000} step="any"
            value={dose.distance ?? ""} onChange={e => update("distance", e.target.value === "" ? null : Number(e.target.value))} />
          <select aria-label="Distance unit" value={dose.distance_unit ?? "m"} onChange={e => update("distance_unit", e.target.value as DoseDraft["distance_unit"])}>
            {["m", "km", "mi", "yd"].map(unit => <option key={unit}>{unit}</option>)}
          </select></div></label>{number("sets", "Sets (optional)", 100, true)}</>
        : <label className={`${styles.doseField} ${styles.wideField}`}><span>Drill instructions</span>
          <textarea aria-label="Drill instructions" maxLength={500} value={dose.prescription ?? ""} onChange={e => update("prescription", e.target.value)} />
        </label>}
      <TimeField label="Rest" rest value={dose.rest_seconds} onChange={v => update("rest_seconds", v)} />
    </div>
    <details className={styles.advanced} open={coaching ? true : undefined}>
      <summary>Weight, effort{coaching ? " & coaching" : " & tempo"}</summary>
      <div className={styles.doseGrid}>
        <label className={`${styles.doseField} ${styles.wideField}`}><span>Weight / intensity</span>
          <input aria-label="Weight or intensity" maxLength={80} placeholder="e.g. 20 kg" value={dose.load_or_intensity ?? ""} onChange={e => update("load_or_intensity", e.target.value)} />
        </label>
        {number("rpe", "RPE (optional)", 10, true)}
        {dose.mode === "reps" ? <><label className={styles.doseField}><span>Tempo</span><input aria-label="Tempo" maxLength={40} value={dose.tempo ?? ""} onChange={e => update("tempo", e.target.value)} /></label>
          <label className={styles.perSide}><input aria-label="Per side" type="checkbox" checked={dose.per_side ?? false} onChange={e => update("per_side", e.target.checked)} />Per side</label></> : null}
      </div>
      {coaching ? <><label className={styles.coachingField}><span>Cues</span><textarea aria-label="Cues" maxLength={2000} rows={2} value={cueText} onChange={e => setCueText(e.target.value)} /></label>
        <label className={styles.coachingField}><span className="ex-row-stop">Stop rules</span><textarea aria-label="Stop rules" maxLength={2000} rows={2} value={stopText} onChange={e => setStopText(e.target.value)} /></label></> : null}
    </details>
    <button type="submit" className={styles.primary} disabled={!validDose(dose) || busy}>{busy ? "Saving…" : action}</button>
  </form>;
}
