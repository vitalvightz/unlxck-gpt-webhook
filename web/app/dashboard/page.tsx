"use client";

import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { Skeleton } from "@/components/skeleton";
import { useToast } from "@/components/toast-provider";
import { getDashboard, submitDailyCheckin, submitSessionLog } from "@/lib/api";
import type {
  AthleteDashboardState,
  ReadinessState,
  WeeklyDayEntry,
} from "@/lib/types";

const SCALE_OPTIONS = [1, 2, 3, 4, 5] as const;

const READINESS_TONE: Record<ReadinessState, string> = {
  ready: "var(--success-ink, #2e9e5b)",
  caution: "#d9a13b",
  high_fatigue: "#d96a3b",
  injury_flag: "var(--danger-ink, #c43d4b)",
};

const SESSION_TYPE_OPTIONS = [
  { value: "training", label: "Training" },
  { value: "sparring", label: "Sparring" },
  { value: "strength", label: "Strength" },
  { value: "conditioning", label: "Conditioning" },
  { value: "recovery", label: "Recovery" },
];

function describeDay(entry: WeeklyDayEntry | null | undefined): string {
  if (!entry) {
    return "No session information for today.";
  }
  const parts: string[] = [];
  if (entry.status) {
    parts.push(entry.status);
  }
  if (entry.effective_load && entry.effective_load !== "none") {
    parts.push(`${entry.effective_load} load`);
  }
  if (entry.coach_note) {
    parts.push(entry.coach_note);
  }
  return parts.length ? parts.join(" — ") : "Rest / no scheduled load.";
}

function ScaleField({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className="field">
      <label>
        {label} <span style={{ color: "var(--text-muted)" }}>({hint})</span>
      </label>
      <div style={{ display: "flex", gap: 8 }}>
        {SCALE_OPTIONS.map((option) => (
          <button
            key={option}
            type="button"
            className={option === value ? "cta" : "secondary-button"}
            style={{ minWidth: 40, padding: "8px 0" }}
            aria-pressed={option === value}
            onClick={() => onChange(option)}
          >
            {option}
          </button>
        ))}
      </div>
    </div>
  );
}

function DashboardScreen() {
  const { session } = useAppSession();
  const { showToast } = useToast();
  const token = session?.access_token ?? null;

  const [dashboard, setDashboard] = useState<AthleteDashboardState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [readiness, setReadiness] = useState(3);
  const [fatigue, setFatigue] = useState(3);
  const [soreness, setSoreness] = useState(3);
  const [sleepQuality, setSleepQuality] = useState(3);
  const [sleepHours, setSleepHours] = useState("");
  const [injuryNote, setInjuryNote] = useState("");
  const [checkinNotes, setCheckinNotes] = useState("");
  const [isSubmittingCheckin, setIsSubmittingCheckin] = useState(false);

  const [sessionType, setSessionType] = useState("training");
  const [completed, setCompleted] = useState(true);
  const [rpe, setRpe] = useState("");
  const [durationMinutes, setDurationMinutes] = useState("");
  const [sessionNotes, setSessionNotes] = useState("");
  const [isSubmittingLog, setIsSubmittingLog] = useState(false);

  const loadDashboard = useCallback(async () => {
    if (!token) {
      return;
    }
    try {
      const state = await getDashboard(token);
      setDashboard(state);
      setLoadError(null);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Failed to load dashboard.");
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  const readinessTone = useMemo(() => {
    const state = dashboard?.readiness.state ?? "caution";
    return READINESS_TONE[state];
  }, [dashboard]);

  async function handleCheckinSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || isSubmittingCheckin) {
      return;
    }
    setIsSubmittingCheckin(true);
    try {
      const response = await submitDailyCheckin(token, {
        readiness,
        fatigue,
        soreness,
        sleep_quality: sleepQuality,
        sleep_hours: sleepHours.trim() ? Number.parseFloat(sleepHours) : null,
        injury_note: injuryNote.trim(),
        notes: checkinNotes.trim(),
      });
      const headline = response.adaptation_notes[0]?.summary ?? "Check-in saved.";
      showToast(`Status: ${response.readiness.label}. ${headline}`, {
        tone: response.readiness.state === "ready" ? "success" : "info",
      });
      setInjuryNote("");
      setCheckinNotes("");
      await loadDashboard();
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Failed to save check-in.", {
        tone: "error",
      });
    } finally {
      setIsSubmittingCheckin(false);
    }
  }

  async function handleSessionLogSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || isSubmittingLog) {
      return;
    }
    setIsSubmittingLog(true);
    try {
      const response = await submitSessionLog(token, {
        session_type: sessionType,
        completed,
        rpe: rpe.trim() ? Number.parseInt(rpe, 10) : null,
        duration_minutes: durationMinutes.trim() ? Number.parseInt(durationMinutes, 10) : null,
        notes: sessionNotes.trim(),
      });
      const advisory = response.adaptation_notes.find((note) => note.decision !== "keep_plan");
      showToast(advisory ? advisory.summary : "Session logged.", {
        tone: advisory ? "info" : "success",
      });
      setRpe("");
      setDurationMinutes("");
      setSessionNotes("");
      setCompleted(true);
      await loadDashboard();
    } catch (error) {
      showToast(error instanceof Error ? error.message : "Failed to log session.", {
        tone: "error",
      });
    } finally {
      setIsSubmittingLog(false);
    }
  }

  if (isLoading) {
    return (
      <section className="panel" aria-busy="true">
        <Skeleton variant="text" width="40%" />
        <Skeleton variant="block" height={120} />
        <Skeleton variant="block" height={220} />
      </section>
    );
  }

  if (loadError) {
    return (
      <section className="panel">
        <h1>Today</h1>
        <p role="alert">{loadError}</p>
        <button type="button" className="secondary-button" onClick={() => void loadDashboard()}>
          Retry
        </button>
      </section>
    );
  }

  const state = dashboard;
  if (!state) {
    return null;
  }

  return (
    <div style={{ display: "grid", gap: "var(--space-3, 20px)" }}>
      <section className="panel" aria-labelledby="dashboard-status-heading">
        <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
          <h1 id="dashboard-status-heading" style={{ margin: 0 }}>
            Today
          </h1>
          <span
            className="badge"
            style={{ borderColor: readinessTone, color: readinessTone }}
            data-testid="readiness-badge"
          >
            {state.readiness.label}
          </span>
        </header>
        {state.readiness.reasons.length > 0 && (
          <ul style={{ margin: "8px 0 0", paddingLeft: 18, color: "var(--text-secondary)" }}>
            {state.readiness.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        )}
        {state.open_injury_flags.length > 0 && (
          <p role="alert" style={{ color: "var(--danger-ink, #c43d4b)", marginTop: 12 }}>
            Open injury flag{state.open_injury_flags.length === 1 ? "" : "s"}:{" "}
            {state.open_injury_flags.map((flag) => flag.description).join("; ")}
          </p>
        )}
        <div className="review-detail-list" style={{ marginTop: 16 }}>
          <div className="review-detail-row">
            <span>Current plan</span>
            <span>
              {state.plan ? (
                <Link href={`/plans/${state.plan.plan_id}`}>
                  {state.plan.plan_name?.trim() || state.plan.fight_date || "View plan"}
                </Link>
              ) : (
                <Link href="/new-plan">No plan yet — generate one</Link>
              )}
            </span>
          </div>
          {state.current_week && (
            <div className="review-detail-row">
              <span>Current week</span>
              <span>
                {state.current_week.week_label_with_countdown ||
                  `Week ${(state.current_week_index ?? 0) + 1} of ${state.current_week.week_count}` +
                    (state.current_week.phase ? ` — ${state.current_week.phase}` : "")}
              </span>
            </div>
          )}
          <div className="review-detail-row">
            <span>Today&apos;s session</span>
            <span>{describeDay(state.today)}</span>
          </div>
          {state.next_session && (
            <div className="review-detail-row">
              <span>Next session</span>
              <span>
                {state.next_session.weekday_with_label || state.next_session.weekday}:{" "}
                {describeDay(state.next_session)}
              </span>
            </div>
          )}
          <div className="review-detail-row">
            <span>Last 7 days</span>
            <span>
              {state.completion.completed_sessions_7d} completed
              {state.completion.missed_sessions_7d > 0
                ? `, ${state.completion.missed_sessions_7d} missed`
                : ""}
              {` · ${state.completion.checkins_7d} check-in${state.completion.checkins_7d === 1 ? "" : "s"}`}
            </span>
          </div>
        </div>
      </section>

      <section className="panel" aria-labelledby="daily-checkin-heading">
        <h2 id="daily-checkin-heading">Daily check-in</h2>
        {state.checked_in_today ? (
          <p style={{ color: "var(--text-secondary)" }}>
            Checked in today — submit again to update your numbers.
          </p>
        ) : (
          <p style={{ color: "var(--text-secondary)" }}>
            30 seconds: how you feel drives how the plan flexes.
          </p>
        )}
        <form onSubmit={handleCheckinSubmit} style={{ display: "grid", gap: 14 }}>
          <ScaleField label="Readiness" hint="1 wrecked · 5 sharp" value={readiness} onChange={setReadiness} />
          <ScaleField label="Fatigue" hint="1 fresh · 5 exhausted" value={fatigue} onChange={setFatigue} />
          <ScaleField label="Soreness" hint="1 none · 5 severe" value={soreness} onChange={setSoreness} />
          <ScaleField label="Sleep quality" hint="1 awful · 5 great" value={sleepQuality} onChange={setSleepQuality} />
          <div className="field">
            <label htmlFor="sleep-hours">Sleep hours (optional)</label>
            <input
              id="sleep-hours"
              type="number"
              inputMode="decimal"
              min={0}
              max={24}
              step={0.5}
              value={sleepHours}
              onChange={(event) => setSleepHours(event.target.value)}
              placeholder="e.g. 7.5"
            />
          </div>
          <div className="field">
            <label htmlFor="injury-note">Any new pain or injury? (leave blank if none)</label>
            <input
              id="injury-note"
              type="text"
              maxLength={2000}
              value={injuryNote}
              onChange={(event) => setInjuryNote(event.target.value)}
              placeholder="e.g. sharp pain in right knee on pivots"
            />
          </div>
          <div className="field">
            <label htmlFor="checkin-notes">Notes (optional)</label>
            <input
              id="checkin-notes"
              type="text"
              maxLength={2000}
              value={checkinNotes}
              onChange={(event) => setCheckinNotes(event.target.value)}
            />
          </div>
          <button type="submit" className="cta" disabled={isSubmittingCheckin}>
            {isSubmittingCheckin ? "Saving…" : state.checked_in_today ? "Update check-in" : "Submit check-in"}
          </button>
        </form>
      </section>

      <section className="panel" aria-labelledby="session-log-heading">
        <h2 id="session-log-heading">Log a session</h2>
        <form onSubmit={handleSessionLogSubmit} style={{ display: "grid", gap: 14 }}>
          <div className="field">
            <label htmlFor="session-type">Session type</label>
            <select
              id="session-type"
              value={sessionType}
              onChange={(event) => setSessionType(event.target.value)}
            >
              {SESSION_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="session-completed">Completed?</label>
            <div style={{ display: "flex", gap: 8 }}>
              <button
                type="button"
                className={completed ? "cta" : "secondary-button"}
                aria-pressed={completed}
                onClick={() => setCompleted(true)}
              >
                Completed
              </button>
              <button
                type="button"
                className={completed ? "secondary-button" : "cta"}
                aria-pressed={!completed}
                onClick={() => setCompleted(false)}
              >
                Missed
              </button>
            </div>
          </div>
          <div className="field">
            <label htmlFor="session-rpe">RPE (1–10, how hard it felt)</label>
            <input
              id="session-rpe"
              type="number"
              inputMode="numeric"
              min={1}
              max={10}
              value={rpe}
              onChange={(event) => setRpe(event.target.value)}
              placeholder="e.g. 7"
            />
          </div>
          <div className="field">
            <label htmlFor="session-duration">Duration (minutes, optional)</label>
            <input
              id="session-duration"
              type="number"
              inputMode="numeric"
              min={1}
              max={600}
              value={durationMinutes}
              onChange={(event) => setDurationMinutes(event.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="session-notes">Notes (optional)</label>
            <input
              id="session-notes"
              type="text"
              maxLength={2000}
              value={sessionNotes}
              onChange={(event) => setSessionNotes(event.target.value)}
            />
          </div>
          <button type="submit" className="cta" disabled={isSubmittingLog}>
            {isSubmittingLog ? "Saving…" : "Log session"}
          </button>
        </form>
      </section>

      {state.current_week && state.current_week.days.length > 0 && (
        <section className="panel" aria-labelledby="week-overview-heading">
          <h2 id="week-overview-heading">This week</h2>
          <div className="review-detail-list">
            {state.current_week.days.map((day) => (
              <div className="review-detail-row" key={`${day.weekday}-${day.calendar_date ?? ""}`}>
                <span>{day.weekday_with_label || day.weekday}</span>
                <span>{describeDay(day)}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {state.recent_adaptation_notes.length > 0 && (
        <section className="panel" aria-labelledby="adaptation-heading">
          <h2 id="adaptation-heading">Recent adjustments</h2>
          <ul style={{ margin: 0, paddingLeft: 18, display: "grid", gap: 6 }}>
            {state.recent_adaptation_notes.map((note) => (
              <li key={note.id}>
                {note.summary}
                <span style={{ color: "var(--text-muted)" }}> ({note.decision.replace(/_/g, " ")})</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

export default function DashboardPage() {
  return (
    <RequireAuth>
      <DashboardScreen />
    </RequireAuth>
  );
}
