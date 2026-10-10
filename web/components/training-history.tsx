"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";
import { deleteExternalTraining, editExternalTraining, getTrainingHistory, logExternalTraining } from "@/lib/api";
import { formatAppDate } from "@/lib/date-format";
import {
  TRAINING_ACTIVITIES, TRAINING_EFFORTS, sortTrainingHistory,
  type TrainingActivity, type TrainingEffort, type TrainingHistorySession,
} from "@/lib/training-history";
import styles from "./training-history.module.css";
import planStyles from "./plans/plans.module.css";

const label = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);

export function TrainingHistory({ accessToken }: { accessToken: string | null }) {
  return accessToken ? <TrainingHistoryContent key={accessToken} accessToken={accessToken} /> : null;
}

function TrainingHistoryContent({ accessToken }: { accessToken: string }) {
  const [rows, setRows] = useState<TrainingHistorySession[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [activity, setActivity] = useState<TrainingActivity | "">("");
  const [duration, setDuration] = useState("");
  const [effort, setEffort] = useState<TrainingEffort | "">("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const requestId = useRef<string | null>(null);
  const currentToken = useRef<string | null>(accessToken);
  const activityInput = useRef<HTMLSelectElement>(null);

  useEffect(() => {
    currentToken.current = accessToken;
    let active = true;
    void getTrainingHistory(accessToken).then(result => {
      if (active) setRows(result.sessions);
    }).catch(reason => {
      if (active) setHistoryError(reason instanceof Error ? reason.message : "Unable to load training history.");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; currentToken.current = null; };
  }, [accessToken]);

  useEffect(() => { if (open) activityInput.current?.focus(); }, [open]);

  function startEdit(row?: TrainingHistorySession) {
    setEditing(row?.id ?? null);
    setActivity(row?.activity ?? "");
    setDuration(row?.duration_minutes?.toString() ?? "");
    setEffort(row?.effort ?? "");
    requestId.current = null;
    setError(null);
    setSaved(false);
    setOpen(true);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!accessToken || busy || !activity || !effort) return;
    const minutes = Number(duration);
    if (!Number.isInteger(minutes) || minutes < 1 || minutes > 600) {
      setError("Enter a whole number from 1 to 600 minutes."); return;
    }
    const token = accessToken;
    setBusy(true);
    setError(null);
    try {
      const body = { activity, duration_minutes: minutes, effort };
      const row = editing
        ? await editExternalTraining(token, editing, body)
        : await logExternalTraining(token, { ...body, client_request_id: requestId.current ??= crypto.randomUUID() });
      if (currentToken.current !== token) return;
      setRows(previous => sortTrainingHistory([row, ...previous.filter(item => !(item.source === row.source && item.id === row.id))]));
      requestId.current = null;
      setOpen(false);
      setEditing(null);
      setSaved(true);
    } catch (reason) {
      if (currentToken.current === token) setError(reason instanceof Error ? reason.message : "Unable to save session. Try again.");
    } finally { if (currentToken.current === token) setBusy(false); }
  }

  async function remove(row: TrainingHistorySession) {
    if (!accessToken || busy) return;
    const token = accessToken;
    setBusy(true);
    setError(null);
    try {
      await deleteExternalTraining(token, row.id);
      if (currentToken.current !== token) return;
      setRows(previous => previous.filter(item => !(item.source === "external" && item.id === row.id)));
      if (editing === row.id) { setOpen(false); setEditing(null); }
      setSaved(false);
    } catch (reason) {
      if (currentToken.current === token) setError(reason instanceof Error ? reason.message : "Unable to delete session. Try again.");
    } finally { if (currentToken.current === token) setBusy(false); }
  }

  if (!accessToken) return null;
  return (
    <section className={`${planStyles.campCard} ${styles.training}`} aria-label="Your Training">
      <div className={`${planStyles.campHead} ${styles.heading}`}>
        <div><p className={planStyles.eyebrow}>UNLXCK / PLAN</p><h2>Your Training</h2></div>
        <button className="secondary-button" type="button" onClick={() => startEdit()} disabled={busy} aria-expanded={open}>Log Training</button>
      </div>
      {open ? (
        <form className={styles.form} onSubmit={save} aria-label={editing ? "Edit training" : "Log Training"}>
          <label className="field"><span>Activity</span>
            <select ref={activityInput} required value={activity} disabled={busy} onChange={event => { setActivity(event.target.value as TrainingActivity); requestId.current = null; }}>
              <option value="">Select activity</option>
              {TRAINING_ACTIVITIES.map(value => <option key={value} value={value}>{label(value)}</option>)}
            </select>
          </label>
          <label className="field"><span>Duration (minutes)</span>
            <input type="number" inputMode="numeric" required min={1} max={600} step={1} value={duration} disabled={busy} onChange={event => { setDuration(event.target.value); requestId.current = null; }} />
          </label>
          <label className="field"><span>Effort</span>
            <select required value={effort} disabled={busy} onChange={event => { setEffort(event.target.value as TrainingEffort); requestId.current = null; }}>
              <option value="">Select effort</option>
              {TRAINING_EFFORTS.map(value => <option key={value} value={value}>{label(value)}</option>)}
            </select>
          </label>
          <div className={styles.actions}>
            <button className="cta" type="submit" disabled={busy}>{busy ? "Saving…" : "Save Session"}</button>
            <button className="ghost-button" type="button" disabled={busy} onClick={() => { setOpen(false); setEditing(null); setError(null); }}>Cancel</button>
          </div>
        </form>
      ) : null}
      {error ? <p className="error-banner" role="alert">{error}</p> : null}
      {saved ? <p className="muted" role="status">Session saved.</p> : null}
      {historyError ? <p className="error-banner" role="alert">{historyError}</p> : null}
      {loading ? <p className="muted" role="status">Loading training history…</p> : rows.length ? (
        <ul className={styles.history} aria-label="Training history">
          {rows.map(row => (
            <li key={`${row.source}-${row.id}`} className={styles.row}>
              <div className={styles.copy}>
                <p className={styles.date}>{formatAppDate(row.training_day)}</p>
                <h3>{row.title}</h3>
                <p className="muted">{row.source === "external" ? "Added by you" : "Unlxck"} · {row.status === "modified" ? "Completed with changes" : "Completed"}
                  {row.duration_minutes ? ` · ${row.duration_minutes} min` : ""}{row.effort ? ` · ${label(row.effort)}` : ""}</p>
              </div>
              {row.source === "external" ? <div className={styles.actions}>
                <button className="ghost-button" type="button" disabled={busy} aria-label={`Edit ${row.title}`} onClick={() => startEdit(row)}>Edit</button>
                <button className="ghost-button" type="button" disabled={busy} aria-label={`Delete ${row.title}`} onClick={() => void remove(row)}>Delete</button>
              </div> : null}
            </li>
          ))}
        </ul>
      ) : <p className="muted">Record completed training from your coach or your own routine.</p>}
    </section>
  );
}
