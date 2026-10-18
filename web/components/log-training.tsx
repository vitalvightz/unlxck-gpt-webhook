"use client";

import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import { CustomSelect } from "./custom-select";
import { ApiError, editExternalTraining, getTrainingHistory, logExternalTraining } from "@/lib/api";
import { lockOverlayScroll } from "@/lib/overlay-scroll-lock";
import { formatAppDate } from "@/lib/date-format";
import {
  TRAINING_ACTIVITIES, TRAINING_EFFORTS, canRepeatTraining, latestRepeatableTraining,
  type TrainingActivity, type TrainingEffort, type TrainingHistorySession,
} from "@/lib/training-history";
import styles from "./log-training.module.css";
import { TrainingActionContent } from "./training-action-tile";
import tileStyles from "./training-action-tile.module.css";

const label = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);

type Props = { accessToken: string | null; entry?: TrainingHistorySession; repeatEntry?: TrainingHistorySession; recent?: boolean; onSaved?: (row: TrainingHistorySession) => void; variant?: "compact" | "tile" };

export function LogTraining(props: Props) {
  return props.accessToken ? <LogTrainingContent key={props.accessToken} {...props} accessToken={props.accessToken} /> : null;
}

function LogTrainingContent({ accessToken, entry, repeatEntry, recent = false, onSaved, variant = "compact" }: Props & { accessToken: string }) {
  const [open, setOpen] = useState(false);
  const editing = entry?.id;
  const [lastSession, setLastSession] = useState<TrainingHistorySession>();
  const repeatSource = repeatEntry && canRepeatTraining(repeatEntry) ? repeatEntry : recent ? lastSession : undefined;
  const [repeating, setRepeating] = useState(false);
  const saving = useRef(false);

  useEffect(() => {
    if (!recent) return;
    let cancelled = false;
    void getTrainingHistory(accessToken).then(({ sessions }) => {
      if (!cancelled) {
        const latest = latestRepeatableTraining(sessions);
        setLastSession(current => current ?? latest);
      }
    }).catch(() => { /* The simple action remains available if history cannot load. */ });
    return () => { cancelled = true; };
  }, [accessToken, recent]);
  const [activity, setActivity] = useState<TrainingActivity | "">("");
  const [duration, setDuration] = useState("");
  const [effort, setEffort] = useState<TrainingEffort | "">("");
  const [trainingDay, setTrainingDay] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [saved, setSaved] = useState<string | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const requestId = useRef<string | null>(null);
  const currentToken = useRef<string | null>(accessToken);
  const fieldId = useId();

  useEffect(() => {
    currentToken.current = accessToken;
    return () => { currentToken.current = null; };
  }, [accessToken]);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const release = lockOverlayScroll();
    dialog.current?.showModal();
    dialog.current?.querySelector<HTMLButtonElement>(repeating ? `[id="${fieldId}-effort"]` : '[role="combobox"]')?.focus();
    return () => { release(); previous?.focus(); };
  }, [open, repeating, fieldId]);

  useEffect(() => {
    if (!saved) return;
    const timer = setTimeout(() => setSaved(null), 5000);
    return () => clearTimeout(timer);
  }, [saved]);

  function startEdit(row?: TrainingHistorySession, repeat = false) {
    setRepeating(repeat);
    setActivity(row?.activity ?? "");
    setDuration(row?.duration_minutes?.toString() ?? "");
    setEffort(repeat ? "" : row?.effort ?? "");
    setTrainingDay("");
    requestId.current = null;
    setError(null);
    setSaved(null);
    setOpen(true);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!accessToken || saving.current) return;
    if (!activity || !effort) {
      setError("Select an activity and effort."); return;
    }
    const minutes = Number(duration);
    if (!Number.isInteger(minutes) || minutes < 1 || minutes > 600) {
      setError("Enter a whole number from 1 to 600 minutes."); return;
    }
    const token = accessToken;
    saving.current = true;
    setBusy(true);
    setError(null);
    try {
      const body = { activity, duration_minutes: minutes, effort };
      const row = editing
        ? await editExternalTraining(token, editing, body)
        : await logExternalTraining(token, { ...body, ...(trainingDay ? { training_day: trainingDay } : {}), client_request_id: requestId.current ??= crypto.randomUUID() });
      if (currentToken.current !== token) return;
      if (recent) setLastSession(current => latestRepeatableTraining([row, ...(current ? [current] : [])]));
      onSaved?.(row);
      requestId.current = null;
      setOpen(false);
      setSaved(`${row.title} logged successfully. Saved to Training History.`);
    } catch (reason) {
      if (currentToken.current === token) setError(reason instanceof ApiError && reason.status === 401 ? "Your session expired. Sign in again to log training." : reason instanceof Error ? reason.message.replace("The plan service", "The training service") : "Unable to save session. Try again.");
    } finally { saving.current = false; if (currentToken.current === token) setBusy(false); }
  }

  return (
    <div className={entry || repeatEntry ? styles.editControl : styles.training} role={entry || repeatEntry ? undefined : "region"} aria-label={entry ? `Manage ${entry.title}` : "Log Training"}>
      {repeatSource ? <button className={repeatEntry ? styles.repeatButton : styles.actionRow} type="button" onClick={() => startEdit(repeatSource, true)} aria-haspopup="dialog" aria-label={repeatEntry ? `Repeat ${repeatSource.title}` : "Repeat last session"} aria-describedby={!repeatEntry ? `${fieldId}-recent` : undefined}>
        {repeatEntry ? "Repeat" : <span><strong>Repeat last session</strong><span id={`${fieldId}-recent`}>{label(repeatSource.activity!)} · {repeatSource.duration_minutes} min<span className="muted">Last recorded: {label(repeatSource.effort!)} effort</span></span><span className="muted">Review and log today’s session</span></span>}
      </button> : null}
      {repeatEntry ? null : entry ? <button className={styles.editButton} type="button" onClick={() => startEdit(entry)} aria-haspopup="dialog" aria-label={`Edit ${entry.title}`} title="Edit session">
        <svg className="ex-log-edit-icon" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false"><path d="M4 20h4L18.5 9.5a2.12 2.12 0 0 0-3-3L5 17v3Z" /><path d="m14.5 7.5 3 3" /></svg>
      </button> :
        <button className={variant === "tile" ? `${tileStyles.tile} ${tileStyles.log}` : styles.actionRow} type="button" onClick={() => startEdit()} aria-haspopup="dialog" aria-label="Log Training">
          {variant === "tile" ? <TrainingActionContent kind="log" /> : <><span><strong>{recent && repeatSource ? "Log another session" : "Log Training"}</strong><span className="muted">Sparring, boxing, roadwork, strength and more.</span></span><span aria-hidden="true">+</span></>}
        </button>}
      {open ? (
        <dialog ref={dialog} className={styles.dialog} aria-label={editing ? "Edit training" : "Log Training"} onCancel={event => { if (busy) event.preventDefault(); else setOpen(false); }}>
        <h2>{editing ? "Edit training" : "Log Training"}</h2>
        {repeating ? <p className="muted" id={`${fieldId}-repeat`}>Activity and duration copied. Confirm today’s effort.</p> : null}
        <form className={styles.form} onSubmit={save} aria-label={editing ? "Edit training" : "Log Training"}>
          <div className="field"><label htmlFor={`${fieldId}-activity`}>Activity</label>
            <CustomSelect id={`${fieldId}-activity`} value={activity} disabled={busy} placeholder="Select activity"
              options={TRAINING_ACTIVITIES.map(value => ({ value, label: label(value) }))}
              onChange={value => { setActivity(value as TrainingActivity); requestId.current = null; }} />
          </div>
          <label className="field"><span>Duration (minutes)</span>
            <input type="number" inputMode="numeric" required min={1} max={600} step={1} value={duration} disabled={busy} onChange={event => { setDuration(event.target.value); requestId.current = null; }} />
          </label>
          <div className="field"><label htmlFor={`${fieldId}-effort`}>Effort</label>
            <CustomSelect id={`${fieldId}-effort`} value={effort} disabled={busy} placeholder="Select effort"
              describedBy={repeating ? `${fieldId}-repeat` : undefined}
              options={TRAINING_EFFORTS.map(value => ({ value, label: label(value) }))}
              onChange={value => { setEffort(value as TrainingEffort); requestId.current = null; }} />
          </div>
          {!editing ? <details className={styles.dateChoice}>
            <summary>Training date · {trainingDay ? formatAppDate(trainingDay) : "Current day"}</summary>
            <label className="field"><span>Training date (optional)</span>
              <input type="date" value={trainingDay} disabled={busy} onChange={event => { setTrainingDay(event.target.value); requestId.current = null; }} />
            </label>
            <p className="muted">Leave blank for your current training day.</p>
          </details> : null}
          <div className={styles.actions}>
            <button className="cta" type="submit" disabled={busy}>{busy ? "Saving…" : "Save Session"}</button>
            <button className="ghost-button" type="button" disabled={busy} onClick={() => { setOpen(false); setError(null); }}>Cancel</button>
          </div>
          {error ? <p className="error-banner" role="alert">{error}</p> : null}
        </form>
        </dialog>
      ) : null}
      {saved && !entry && !repeatEntry ? <p className="muted" role="status">{saved}</p> : null}
    </div>
  );
}
