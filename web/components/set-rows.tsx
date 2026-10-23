"use client";

import { useState } from "react";
import type { ExerciseSetResult } from "@/lib/types";
import { blankSet, MAX_SETS, setSummary, type SetDraft } from "@/lib/set-entries";
import styles from "./set-rows.module.css";

/** One visual language for live logging, exercise editing and saved history. */
export function SetRows({ rows, onChange, unit = "kg", onUnitChange, showLoad = true, disabled = false,
  active, completed = 0, compact = false, editableCount = true, invalid = [], repsHint }: {
  rows: SetDraft[]; onChange: (rows: SetDraft[]) => void; unit?: string; onUnitChange?: () => void;
  showLoad?: boolean; disabled?: boolean; active?: number; completed?: number; compact?: boolean;
  editableCount?: boolean; invalid?: number[]; repsHint?: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const [changed, setChanged] = useState<{ index: number; field: "reps" | "load" } | null>(null);
  const all = !compact || expanded;
  const shown = all ? rows.map((row, index) => ({ row, index })) : [{ row: rows[active ?? 0] ?? blankSet(), index: active ?? 0 }];
  return <div className={styles.root}>
    <div className={styles.head} data-load={showLoad}>
      <span>Set</span>
      {showLoad ? onUnitChange ? <button type="button" disabled={disabled} onClick={onUnitChange} aria-label={`Load unit: ${unit}. Change unit`}>{unit}</button> : <span>{unit}</span> : null}
      <span>Reps</span><span />
    </div>
    <ol className={styles.rows} aria-label="Set results">
      {shown.map(({ row, index }) => <li key={index} className={styles.row} data-load={showLoad} data-active={active === index} data-complete={index < completed}>
        <span className={styles.number}>{index + 1}</span>
        {([...(showLoad ? ["load" as const] : []), "reps" as const]).map(field => <input key={field} type="text" inputMode={field === "reps" ? "numeric" : "decimal"}
          autoComplete="off" enterKeyHint="done" maxLength={8} disabled={disabled} value={row[field]}
          placeholder={field === "reps" ? repsHint ?? "–" : "–"} aria-label={`${field === "load" ? `Load ${unit}` : "Reps"}, set ${index + 1}`}
          aria-invalid={invalid.includes(index) || undefined} onFocus={event => event.target.select()}
          onChange={event => { const value = event.target.value; onChange(rows.map((entry, at) => at === index ? { ...entry, [field]: value } : entry)); setChanged({ index, field }); }} />)}
        {index < completed ? <span className={styles.check} aria-label={`Set ${index + 1} completed`}>✓</span> : editableCount && rows.length > 1 && all
          ? <button className={styles.remove} type="button" aria-label={`Remove set ${index + 1}`} disabled={disabled} onClick={() => { onChange(rows.filter((_, at) => at !== index)); setChanged(null); }}>×</button>
          : <span className={styles.pending} aria-hidden="true">{active === index ? "•" : ""}</span>}
      </li>)}
    </ol>
    <div className={styles.actions}>
      {compact ? <button type="button" aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>{expanded ? "Current set" : `All ${rows.length} sets`}</button> : null}
      {editableCount && all ? <button type="button" disabled={disabled || rows.length >= MAX_SETS} onClick={() => onChange([...rows, { ...(rows.at(-1) ?? blankSet()) }])}>+ Add set</button> : null}
      {changed !== null && changed.index < rows.length - 1 ? <button type="button" disabled={disabled} onClick={() => {
        onChange(rows.map((row, index) => index > changed.index && index >= completed ? { ...row, [changed.field]: rows[changed.index][changed.field] } : row)); setChanged(null);
      }}>Apply to remaining sets</button> : null}
    </div>
    {invalid.length ? <p className={styles.error} role="alert">Check the highlighted sets. Use whole reps and a valid load.</p> : null}
  </div>;
}

export function SetResults({ entries }: { entries: readonly ExerciseSetResult[] }) {
  const showLoad = entries.some(entry => entry.load != null);
  const unit = entries.find(entry => entry.load)?.load?.unit ?? "kg";
  return <details className={styles.results}>
    <summary>{setSummary(entries)}</summary>
    <div className={styles.head} data-load={showLoad}><span>Set</span>{showLoad ? <span>{unit}</span> : null}<span>Reps</span><span /></div>
    <ol className={styles.rows} aria-label="Recorded sets">{entries.map((entry, index) => <li key={index} className={styles.row} data-load={showLoad}>
      <span className={styles.number}>{index + 1}</span>{showLoad ? <span className={styles.value}>{entry.load ? entry.load.value : "–"}</span> : null}
      <span className={styles.value}>{entry.reps ?? "–"}</span><span className={styles.check} aria-label="Completed">✓</span>
    </li>)}</ol>
  </details>;
}
