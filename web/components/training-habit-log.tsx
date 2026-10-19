"use client";

import { useEffect, useRef, useState } from "react";
import { useAppSession } from "./auth-provider";
import { LogTraining } from "./log-training";
import { ApiError, getManualTrainingHistory, getTrainingHistory, getMe, updateMe } from "@/lib/api";
import {
  decideTrainingHabit, EMPTY_TRAINING_HABITS, HABIT_WEEKDAYS, habitTrainingDay, learnTrainingHabits,
  type TrainingHabitDecision, type TrainingHabitPreferences,
} from "@/lib/training-habits";
import type { TrainingHistorySession } from "@/lib/training-history";
import { trainingLabel } from "@/lib/training-disciplines";
import type { TodayCommandView } from "@/lib/types";
import styles from "./training-habit-log.module.css";

// The logger is the lead action when no programme prescribes today's work.
// onLoggedToday receives null while shared history is loading or unavailable.
type Props = { accessToken: string | null; state: TodayCommandView | null; onSaved: () => void; variant?: "primary" | "compact"; onLoggedToday?: (logged: boolean | null) => void };
export function TrainingHabitLog(props: Props) {
  return props.accessToken ? <HabitLogContent key={props.accessToken} {...props} accessToken={props.accessToken} /> : null;
}

function HabitLogContent({ accessToken, state, onSaved, variant = "compact", onLoggedToday }: Props & { accessToken: string }) {
  const { me, replaceMe } = useAppSession();
  const [history, setHistory] = useState<TrainingHistorySession[]>([]);
  const [sharedHistory, setSharedHistory] = useState<TrainingHistorySession[]>([]);
  const [sharedHistoryError, setSharedHistoryError] = useState(false);
  const [historyError, setHistoryError] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);
  const active = useRef(true);
  const historyWrites = useRef(0);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const profile = me?.profile;
  // Suggestions are always on; athletes steer them with "Yes, usually" / "Not always".
  const preferences = { ...(profile?.training_habits ?? EMPTY_TRAINING_HABITS), enabled: true };
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
    void getManualTrainingHistory(accessToken).then(({ sessions }) => {
      if (!Array.isArray(sessions)) throw new Error("Invalid history");
      if (!cancelled) {
        setHistory(current => initialWrites === historyWrites.current ? sessions
          : [...current, ...sessions.filter(row => !current.some(item => item.id === row.id))]);
        setHistoryError(false);
      }
    }).catch(() => { if (!cancelled) setHistoryError(true); });
    return () => { cancelled = true; };
  }, [accessToken]);

  useEffect(() => {
    let cancelled = false;
    const initialWrites = historyWrites.current;
    void getTrainingHistory(accessToken).then(({ sessions }) => {
      if (!Array.isArray(sessions)) throw new Error("Invalid history");
      if (!cancelled) {
        setSharedHistory(current => initialWrites === historyWrites.current ? sessions
          : [...current, ...sessions.filter(row => !current.some(item => item.id === row.id && item.source === row.source))]);
        setSharedHistoryError(false);
      }
    }).catch(() => { if (!cancelled) setSharedHistoryError(true); })
      .finally(() => { if (!cancelled) setHistoryLoading(false); });
    return () => { cancelled = true; };
  }, [accessToken]);

  const trainingDay = state?.today.training_day || today;
  const loggedToday = historyLoading || sharedHistoryError ? null
    : sharedHistory.some(row => row.training_day === trainingDay && row.status !== "skipped");
  useEffect(() => { onLoggedToday?.(loggedToday); }, [loggedToday, onLoggedToday]);

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
              && rule.activity === item.activity && (rule.sport ?? null) === (item.sport ?? null)
              && (rule.session_type ?? null) === (item.session_type ?? null) && rule.duration_minutes === item.duration_minutes
              && rule.state === item.state && rule.decided_on === item.decided_on))) {
            setNotice(message); return;
          }
        } catch { /* Keep the conflict visible if the fresh read also fails. */ }
      }
      setError(reason instanceof ApiError && reason.status === 401 ? "Sign in again to save routines."
        : reason instanceof Error ? reason.message : "Couldn’t save. Try again.");
    } finally { saving.current = false; if (active.current) setBusy(false); }
  }

  function decide(confirmed: boolean) {
    if (!prompt) return;
    void persist(decideTrainingHabit(preferences, {
      weekday: prompt.weekday, activity: prompt.activity, duration_minutes: prompt.duration_minutes,
      ...(prompt.sport ? { sport: prompt.sport, session_type: prompt.session_type ?? null } : {}),
      state: confirmed ? "confirmed" : "dismissed", decided_on: today,
    }, confirmed ? prompt.replace : undefined), confirmed ? "Routine saved." : "We won’t ask again.");
  }

  return <div className={styles.root} aria-busy={busy || undefined}>
    <LogTraining accessToken={accessToken} recent history={history} variant={variant} onSparringReported={onSaved}
      quickSession={suggestion ? { ...suggestion, effort: suggestion.source?.effort } : undefined}
      onSaved={row => {
        historyWrites.current++;
        setHistory(current => [row, ...current.filter(item => item.id !== row.id)]);
        setSharedHistory(current => [row, ...current.filter(item => item.id !== row.id || item.source !== row.source)]);
        onSaved();
      }} />
    {prompt ? <div className={styles.prompt}>
      <p className={styles.eyebrow}>{prompt.replace ? "Routine changed?" : "Noticed a pattern"}</p>
      <p className={styles.question}>{prompt.replace ? `Switch ${HABIT_WEEKDAYS[prompt.weekday]} to ${trainingLabel(prompt)}?` : `${trainingLabel(prompt)} every ${HABIT_WEEKDAYS[prompt.weekday]}?`}</p>
      <p className={styles.evidence}>Logged two weeks in a row.</p>
      <div className={styles.actions}>
        <button type="button" className="secondary-button" disabled={busy} onClick={() => decide(true)}>{prompt.replace ? "Yes, update" : "Yes, usually"}</button>
        <button type="button" className="ghost-button" disabled={busy} onClick={() => decide(false)}>Not always</button>
      </div>
    </div> : null}
    {notice ? <p className={styles.evidence} role="status">{notice}</p> : null}
    {error ? <p className="error-banner" role="alert">{error}</p> : null}
  </div>;
}
