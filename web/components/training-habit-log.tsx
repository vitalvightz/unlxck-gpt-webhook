"use client";

import { useEffect, useRef, useState } from "react";
import { useAppSession } from "./auth-provider";
import { LogTraining } from "./log-training";
import { ApiError, getManualTrainingHistory, getTrainingHistory, getMe, updateMe } from "@/lib/api";
import { TrackingHistoryPreview } from "./tracking-history-preview";
import {
  decideTrainingHabit, EMPTY_TRAINING_HABITS, HABIT_WEEKDAYS, habitTrainingDay, learnTrainingHabits,
  type TrainingHabitDecision, type TrainingHabitPreferences,
} from "@/lib/training-habits";
import type { TrainingActivity, TrainingHistorySession } from "@/lib/training-history";
import { TRAINING_ACTIVITIES } from "@/lib/training-history";
import type { TodayCommandView } from "@/lib/types";
import styles from "./training-habit-log.module.css";

const label = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);

type Props = { accessToken: string | null; state: TodayCommandView | null; onSaved: () => void; trackingFirst?: boolean };
export function TrainingHabitLog(props: Props) {
  return props.accessToken ? <HabitLogContent key={props.accessToken} {...props} accessToken={props.accessToken} /> : null;
}

function HabitLogContent({ accessToken, state, onSaved, trackingFirst = false }: Props & { accessToken: string }) {
  const { me, replaceMe } = useAppSession();
  const [history, setHistory] = useState<TrainingHistorySession[]>([]);
  const [historyError, setHistoryError] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const [pendingEnabled, setPendingEnabled] = useState<boolean | null>(null);
  const saving = useRef(false);
  const active = useRef(true);
  const historyWrites = useRef(0);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const profile = me?.profile;
  const preferences = profile?.training_habits ?? EMPTY_TRAINING_HABITS;
  const [now, setNow] = useState(() => new Date());
  const today = habitTrainingDay(now, profile?.athlete_timezone);

  useEffect(() => {
    const update = () => setNow(new Date());
    const interval = window.setInterval(update, 60_000);
    window.addEventListener("focus", update);
    return () => { window.clearInterval(interval); window.removeEventListener("focus", update); };
  }, []);

  useEffect(() => {
    active.current = true;
    return () => { active.current = false; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const initialWrites = historyWrites.current;
    void (trackingFirst ? getTrainingHistory(accessToken) : getManualTrainingHistory(accessToken)).then(({ sessions }) => {
      if (!Array.isArray(sessions)) throw new Error("Invalid history");
      if (!cancelled) {
        setHistory(current => initialWrites === historyWrites.current ? sessions
          : [...current, ...sessions.filter(row => !current.some(item => item.id === row.id))]);
        setHistoryError(false);
      }
    }).catch(() => { if (!cancelled) setHistoryError(true); })
      .finally(() => { if (!cancelled) setHistoryLoading(false); });
    return () => { cancelled = true; };
  }, [accessToken, reload, trackingFirst]);

  // Coach-declared work and the live safety decision outrank learned logging guesses.
  const coachScheduled = state?.today.session_scope === "today" && Boolean(
    state.today.next_session.coach_led_contact || ["sparring", "light_combat", "coach_led", "technical"].includes(state.today.next_session.session_type ?? ""),
  );
  const restricted = Boolean(profile?.health_consent_granted === false || state?.live_prescription?.safety_hold || state?.today.primary_safety_notice
    || (state?.open_injuries?.length ?? 0) > 0
    || ["stop", "pull_back", "modify"].includes(state?.today.decision_tier ?? "")
    || ["pull_back", "modify"].includes(state?.today.recommendation_state ?? ""));
  // This is permission to display a logging guess, never permission to start contact.
  const allowSparring = state?.today.decision_tier === "green"
    && state.effective_clinician_clearance?.level === "train_contact"
    && state.effective_clinician_clearance.requires_update === false;
  const learned = learnTrainingHabits(history, today, preferences, { coachScheduled, restricted, allowSparring, truncated: history.length >= 200, historyUnavailable: historyError });
  const suggestion = profile?.training_habits ? learned.suggestion : undefined;
  const prompt = profile?.training_habits && !historyError ? learned.prompt : undefined;

  async function persist(next: TrainingHabitPreferences, message: string) {
    if (saving.current || !profile) return;
    saving.current = true; setBusy(true); setError(null); setNotice(null);
    try {
      const result = await updateMe(accessToken, { training_habits: next, training_habits_revision: profile.training_habits_revision ?? 0 });
      if (!result.profile.training_habits || result.profile.training_habits_revision !== (profile.training_habits_revision ?? 0) + 1) {
        throw new Error("Routine settings unavailable. Try again.");
      }
      if (active.current) { replaceMe(result); setNotice(message); }
    } catch (reason) {
      if (!active.current) return;
      if (reason instanceof ApiError && reason.status === 409) {
        try {
          const latest = await getMe(accessToken);
          if (!active.current) return;
          replaceMe(latest);
          const saved = latest.profile.training_habits;
          // A retry after a lost response may already have saved this exact intention.
          if (saved?.enabled === next.enabled && saved.decisions.length === next.decisions.length
            && next.decisions.every(item => saved.decisions.some(rule => rule.weekday === item.weekday
              && rule.activity === item.activity && rule.duration_minutes === item.duration_minutes
              && rule.state === item.state && rule.decided_on === item.decided_on))) {
            setNotice(message); return;
          }
        } catch { /* Keep the conflict visible if the fresh read also fails. */ }
      }
      setError(reason instanceof ApiError && reason.status === 401 ? "Sign in again to save routines."
        : reason instanceof Error ? reason.message : "Couldn’t save. Try again.");
    } finally { saving.current = false; if (active.current) { setBusy(false); setPendingEnabled(null); } }
  }

  function decide(confirmed: boolean) {
    if (!prompt) return;
    void persist(decideTrainingHabit(preferences, {
      weekday: prompt.weekday, activity: prompt.activity, duration_minutes: prompt.duration_minutes,
      state: confirmed ? "confirmed" : "dismissed", decided_on: today,
    }, confirmed ? prompt.replace : undefined), confirmed ? "Routine saved." : "We won’t ask again.");
  }

  return <div className={styles.root} aria-busy={busy || undefined}>
    <LogTraining accessToken={accessToken} recent history={history} variant={trackingFirst ? "primary" : "compact"}
      quickSession={suggestion ? { ...suggestion, effort: suggestion.source?.effort } : undefined}
      onSaved={row => { historyWrites.current++; setHistory(current => [row, ...current.filter(item => item.id !== row.id)]); onSaved(); }} />
    {trackingFirst ? <TrackingHistoryPreview history={history} loading={historyLoading} error={historyError} onRetry={() => setReload(value => value + 1)} /> : null}
    {prompt ? <div className={styles.prompt}>
      <p className={styles.eyebrow}>{prompt.replace ? "Routine changed?" : "Noticed a pattern"}</p>
      <p className={styles.question}>{prompt.replace ? `Switch ${HABIT_WEEKDAYS[prompt.weekday]} to ${prompt.activity}?` : `${label(prompt.activity)} every ${HABIT_WEEKDAYS[prompt.weekday]}?`}</p>
      <p className={styles.evidence}>Logged two weeks in a row.</p>
      <div className={styles.actions}>
        <button type="button" className="secondary-button" disabled={busy} onClick={() => decide(true)}>{prompt.replace ? "Yes, update" : "Yes, usually"}</button>
        <button type="button" className="ghost-button" disabled={busy} onClick={() => decide(false)}>Not always</button>
      </div>
    </div> : null}
    {profile?.training_habits ? <details className={styles.settings}>
      <summary>Training habits</summary>
      <label className={styles.toggle}><input type="checkbox" checked={pendingEnabled ?? preferences.enabled} disabled={busy}
        onChange={event => {
          if (saving.current) return;
          const enabled = event.target.checked; setPendingEnabled(enabled);
          void persist({ ...preferences, enabled }, enabled ? "Suggestions on." : "Suggestions paused.");
        }} />Suggest from my history</label>
      <p className={styles.evidence}>Logging suggestions. Readiness still applies.</p>
      {preferences.decisions.length ? <ul className={styles.routines}>
        {preferences.decisions.map(item => <li key={`${item.weekday}-${item.activity}-${item.duration_minutes}-${item.decided_on}`}>
          <RoutineEditor item={item} busy={busy} onSave={updated => void persist(decideTrainingHabit(preferences, { ...updated, decided_on: today }, updated.activity !== item.activity ? item : undefined), "Routine updated.")}
            onRemove={() => void persist(decideTrainingHabit(preferences, { ...item, state: "dismissed", decided_on: today }), "Routine removed.")}
            onReset={() => void persist({ ...preferences, decisions: preferences.decisions.filter(rule => rule !== item) }, "Suggestion reset.")} />
        </li>)}
      </ul> : <p className={styles.evidence}>No routines saved.</p>}
      {historyError ? <div role="status"><p className={styles.evidence}>History unavailable.</p><button type="button" className="ghost-button" onClick={() => setReload(value => value + 1)}>Retry history</button></div> : null}
    </details> : null}
    {notice ? <p className={styles.evidence} role="status">{notice}</p> : null}
    {error ? <p className="error-banner" role="alert">{error}</p> : null}
  </div>;
}

function RoutineEditor({ item, busy, onSave, onRemove, onReset }: {
  item: TrainingHabitDecision; busy: boolean; onSave: (item: TrainingHabitDecision) => void; onRemove: () => void; onReset: () => void;
}) {
  const [activity, setActivity] = useState(item.activity);
  const [duration, setDuration] = useState(String(item.duration_minutes));
  const name = `${HABIT_WEEKDAYS[item.weekday]} ${label(item.activity)}`;
  return <div>
    <div className={styles.routineRow}><span>{HABIT_WEEKDAYS[item.weekday]} · {label(item.activity)}</span>
      {item.state === "dismissed" ? <button className="ghost-button" type="button" disabled={busy} onClick={onReset} aria-label={`Suggest ${name} again`}>Suggest again</button> : <button className="ghost-button" type="button" disabled={busy} onClick={onRemove} aria-label={`Remove ${name}`}>Remove</button>}
    </div>
    {item.state === "confirmed" ? <details>
      <summary>Edit · {item.duration_minutes} min</summary>
      <form className={styles.editForm} aria-label={`Edit ${name} routine`} onSubmit={event => {
        event.preventDefault();
        const minutes = Number(duration);
        if (!Number.isInteger(minutes) || minutes < 1 || minutes > 600) return;
        onSave({ ...item, activity, duration_minutes: minutes });
      }}>
        <label>Activity<select value={activity} disabled={busy} onChange={event => setActivity(event.target.value as TrainingActivity)}>{TRAINING_ACTIVITIES.map(value => <option value={value} key={value}>{label(value)}</option>)}</select></label>
        <label>Minutes<input type="number" required min={1} max={600} step={1} value={duration} disabled={busy} onChange={event => setDuration(event.target.value)} /></label>
        <button className="secondary-button" type="submit" disabled={busy}>Save routine</button>
      </form>
    </details> : null}
  </div>;
}
