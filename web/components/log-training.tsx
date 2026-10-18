"use client";

import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import { useAppSession } from "./auth-provider";
import { habitTrainingDay } from "@/lib/training-habits";
import { ApiError, editExternalTraining, getTrainingHistory, logExternalTraining } from "@/lib/api";
import { lockOverlayScroll } from "@/lib/overlay-scroll-lock";
import { formatAppDate } from "@/lib/date-format";
import {
  TRAINING_EFFORTS, canRepeatTraining, latestRepeatableTraining,
  type TrainingActivity, type TrainingEffort, type TrainingHistorySession,
} from "@/lib/training-history";
import styles from "./log-training.module.css";
import { TrainingActionContent } from "./training-action-tile";
import tileStyles from "./training-action-tile.module.css";

const ACTIVITY_PICKS: TrainingActivity[] = ["boxing", "sparring", "strength", "conditioning", "roadwork", "other"];
const DURATION_PICKS = [30, 45, 60, 90];

const label = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);

type Props = { accessToken: string | null; entry?: TrainingHistorySession; repeatEntry?: TrainingHistorySession; recent?: boolean; history?: TrainingHistorySession[]; quickSession?: { activity: TrainingActivity; duration_minutes: number; title: string; effort?: TrainingEffort | null }; onSaved?: (row: TrainingHistorySession) => void; variant?: "compact" | "tile" | "primary" };

export function LogTraining(props: Props) {
  return props.accessToken ? <LogTrainingContent key={props.accessToken} {...props} accessToken={props.accessToken} /> : null;
}

function LogTrainingContent({ accessToken, entry, repeatEntry, recent = false, history, quickSession, onSaved, variant = "compact" }: Props & { accessToken: string }) {
  const [open, setOpen] = useState(false);
  const editing = entry?.id;
  const [lastSession, setLastSession] = useState<TrainingHistorySession>();
  const repeatSource = repeatEntry && canRepeatTraining(repeatEntry) ? repeatEntry : recent ? history ? latestRepeatableTraining(history) : lastSession : undefined;
  const [repeating, setRepeating] = useState(false);
  const { me } = useAppSession();
  const [now, setNow] = useState(() => new Date());
  const today = habitTrainingDay(now, me?.profile.athlete_timezone);
  const [sourceLabel, setSourceLabel] = useState("");
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [customDuration, setCustomDuration] = useState(false);
  const durationInput = useRef<HTMLInputElement>(null);
  const saving = useRef(false);

  useEffect(() => {
    if (!recent || history) return;
    let cancelled = false;
    void getTrainingHistory(accessToken).then(({ sessions }) => {
      if (!cancelled) {
        const latest = latestRepeatableTraining(sessions);
        setLastSession(current => current ?? latest);
      }
    }).catch(() => { /* The simple action remains available if history cannot load. */ });
    return () => { cancelled = true; };
  }, [accessToken, recent, history]);
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
    dialog.current?.querySelector<HTMLButtonElement>(repeating ? '[data-effort]' : '[data-activity][aria-pressed="true"], [data-activity]')?.focus();
    const update = () => {
      setNow(new Date());
      const viewport = window.visualViewport;
      dialog.current?.style.setProperty("--sheet-height", `${viewport?.height ?? window.innerHeight}px`);
      dialog.current?.style.setProperty("--sheet-bottom", `${viewport ? Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop) : 0}px`);
    };
    update();
    const timer = window.setInterval(update, 60_000);
    window.addEventListener("focus", update);
    window.visualViewport?.addEventListener("resize", update);
    window.visualViewport?.addEventListener("scroll", update);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", update);
      window.visualViewport?.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("scroll", update);
      release(); previous?.focus();
    };
  }, [open, repeating, fieldId]);

  useEffect(() => {
    if (!saved) return;
    const timer = setTimeout(() => setSaved(null), 5000);
    return () => clearTimeout(timer);
  }, [saved]);

  function startEdit(row?: Partial<TrainingHistorySession>, repeat = false, source = "From previous session") {
    setRepeating(repeat);
    setSourceLabel(source);
    setDetailsOpen(false);
    setCustomDuration(row?.duration_minutes != null && !DURATION_PICKS.includes(row.duration_minutes));
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
      setError("Select an activity and effort.");
      dialog.current?.querySelector<HTMLButtonElement>(!activity ? '[data-activity]' : '[data-effort]')?.focus();
      return;
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

  const activityAndDuration = <>
    <fieldset className={styles.fieldset} disabled={busy} aria-label="Activity">
      <legend>Activity</legend>
      <div className={styles.activityGrid}>
        {ACTIVITY_PICKS.map(value => <button key={value} type="button" data-activity aria-pressed={activity === value}
          onClick={() => { setActivity(value); if (activity !== value) requestId.current = null; }}>{label(value)}</button>)}
      </div>
    </fieldset>
    <fieldset className={styles.fieldset} disabled={busy} aria-label="Duration">
      <legend>Duration <span className={styles.unit}>min</span></legend>
      <div className={styles.durationGrid}>
        {DURATION_PICKS.map(value => <button key={value} type="button" aria-pressed={!customDuration && duration === String(value)}
          onClick={() => { setDuration(String(value)); setCustomDuration(false); if (Number(duration) !== value) requestId.current = null; }}>{value}</button>)}
        <button type="button" aria-pressed={customDuration} aria-expanded={customDuration} aria-controls={`${fieldId}-duration`}
          onClick={() => { setCustomDuration(true); requestAnimationFrame(() => durationInput.current?.focus()); }}>Custom</button>
      </div>
      {customDuration ? <label className={styles.customDuration}>Duration (minutes)
        <input id={`${fieldId}-duration`} ref={durationInput} type="number" inputMode="numeric" required min={1} max={600} step={1} value={duration}
          onChange={event => { setDuration(event.target.value); requestId.current = null; }} />
      </label> : null}
    </fieldset>
  </>;
  const dateChoice = !editing ? <details className={styles.dateChoice}>
    <summary>Training date · {formatAppDate(trainingDay || today)}</summary>
    <label className={styles.customDuration}>Training date (optional)
      <input type="date" max={today} value={trainingDay} disabled={busy}
        onChange={event => { setTrainingDay(event.target.value); requestId.current = null; }} />
    </label>
    {trainingDay ? <button className={styles.resetDate} type="button" disabled={busy}
      onClick={() => { setTrainingDay(""); requestId.current = null; }}>Use current training day</button> : null}
  </details> : null;

  return (
    <div className={entry || repeatEntry ? styles.editControl : styles.training} role={entry || repeatEntry ? undefined : "region"} aria-label={entry ? `Manage ${entry.title}` : "Log Training"}>
      {quickSession ? <button className={styles.actionRow} type="button" onClick={() => startEdit(quickSession, true, quickSession.title)} aria-haspopup="dialog" aria-label={quickSession.title} aria-describedby={`${fieldId}-quick`}>
        <span><strong>{quickSession.title}</strong><span className="muted" id={`${fieldId}-quick`}>{label(quickSession.activity)} · {quickSession.duration_minutes} min</span></span>
        <svg className={styles.chevron} viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m9 5 7 7-7 7" /></svg>
      </button> : repeatSource ? <button className={repeatEntry ? styles.repeatButton : styles.actionRow} type="button" onClick={() => startEdit(repeatSource, true)} aria-haspopup="dialog" aria-label={repeatEntry ? `Repeat ${repeatSource.title}` : "Repeat last session"} aria-describedby={!repeatEntry ? `${fieldId}-recent` : undefined}>
        {repeatEntry ? "Repeat" : <><span><strong>Repeat last session</strong><span className="muted" id={`${fieldId}-recent`}>{label(repeatSource.activity!)} · {repeatSource.duration_minutes} min</span></span><svg className={styles.chevron} viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="m9 5 7 7-7 7" /></svg></>}
      </button> : null}
      {repeatEntry ? null : entry ? <button className={styles.editButton} type="button" onClick={() => startEdit(entry)} aria-haspopup="dialog" aria-label={`Edit ${entry.title}`} title="Edit session">
        <svg className="ex-log-edit-icon" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false"><path d="M4 20h4L18.5 9.5a2.12 2.12 0 0 0-3-3L5 17v3Z" /><path d="m14.5 7.5 3 3" /></svg>
      </button> :
        <button className={variant === "primary" ? `cta ${styles.primary}` : variant === "tile" ? `${tileStyles.tile} ${tileStyles.log}` : styles.actionRow} type="button" onClick={() => startEdit()} aria-haspopup="dialog" aria-label="Log Training">
          {variant === "primary" ? <><span aria-hidden="true">+</span> Log training</> : variant === "tile" ? <TrainingActionContent kind="log" /> : <><span><strong>{recent && (repeatSource || quickSession) ? "Log another session" : "Log Training"}</strong><span className="muted">Sparring, boxing, roadwork, strength and more.</span></span><span aria-hidden="true">+</span></>}
        </button>}
      {open ? (
        <dialog ref={dialog} className={styles.dialog} aria-label={editing ? "Edit training" : "Log Training"} onCancel={event => { if (busy) event.preventDefault(); else setOpen(false); }}>
        <header className={styles.header}>
          <div><h2>{editing ? "Edit training" : repeating && activity ? `Log ${activity}` : "Log training"}</h2>
            {repeating ? <p className={styles.source}>{duration} min · {sourceLabel}</p> : null}
          </div>
          <button className={styles.close} type="button" aria-label="Close training log" disabled={busy} onClick={() => setOpen(false)}>×</button>
        </header>
        <form className={styles.form} onSubmit={save} aria-label={editing ? "Edit training" : "Log Training"}>
          <div className={styles.body}>
            {!repeating ? activityAndDuration : null}
            <fieldset className={styles.fieldset} disabled={busy} aria-label="Effort">
              <legend>{repeating ? "How hard was it today?" : "Effort"} <span className={styles.unit}>Required</span></legend>
              <div className={styles.effortGrid}>
                {TRAINING_EFFORTS.map(value => <button key={value} type="button" data-effort aria-pressed={effort === value}
                  onClick={() => { setEffort(value); if (effort !== value) requestId.current = null; }}>{label(value)}</button>)}
              </div>
            </fieldset>
            {repeating ? <>
              <button className={styles.detailsToggle} type="button" aria-expanded={detailsOpen} aria-controls={`${fieldId}-details`} disabled={busy}
                onClick={() => setDetailsOpen(value => !value)}>Edit details <span aria-hidden="true">{detailsOpen ? "−" : "+"}</span></button>
              <div id={`${fieldId}-details`} className={styles.expandedDetails} hidden={!detailsOpen}>
                {activityAndDuration}{dateChoice}
              </div>
            </> : dateChoice}
          </div>
          <footer className={styles.actions}>
            {error ? <p className={styles.error} role="alert">{error}</p> : null}
            <button className="cta" type="submit" disabled={busy}>{busy ? "Saving…" : "Save Session"}</button>
          </footer>
        </form>
        </dialog>
      ) : null}
      {saved && !entry && !repeatEntry ? <p className="muted" role="status">{saved}</p> : null}
    </div>
  );
}
