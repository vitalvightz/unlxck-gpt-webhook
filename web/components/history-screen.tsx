"use client";

import { type CSSProperties, useEffect, useState } from "react";

import { useAppSession } from "@/components/auth-provider";
import { EmptyState } from "@/components/empty-state";
import { GlossaryTooltip } from "@/components/glossary-tooltip";
import { Skeleton } from "@/components/skeleton";
import {
  listInjuryFlags,
  listExerciseHistory,
  listSessionCompletionHistory,
  listSparringLogHistory,
  listTodayCheckinHistory,
} from "@/lib/api";
import { EXERCISE_LOG_REASON_LABELS, EXERCISE_LOG_STATUS_LABELS, performanceSummary } from "@/lib/exercise-log";
import { athleteTrainingDayISO } from "@/lib/camp-map";
import { formatAppDate } from "@/lib/date-format";
import {
  checkinChips,
  countRecentBy,
  daysAgoLabel,
  HARD_SPARRING_DAYS_PER_WEEK,
  type HistoryChip,
  injuryReportedTone,
  injurySeverityTone,
  injuryStatusLabel,
  injuryStatusTone,
  recommendationLabel,
  recommendationTone,
  sessionStatusLabel,
  sessionStatusTone,
  sparringIntensityLabel,
  sparringIntensityTone,
  sparringPlanDifference,
  sparringRowMeta,
  sparringWeekNote,
  trainingDaysAgo,
} from "@/lib/history";
import { formatInjuryDetail, normalizeInjuryLabel } from "@/lib/injury-display";
import { loadHistoryWithAuthRecovery } from "@/lib/history-request";
import type { TodayDecisionTone } from "@/lib/today";
import type {
  InjuryFlagRecord,
  ExerciseHistoryResponse,
  SparringLogHistoryResponse,
  TodayCheckinHistoryRecord,
  TodaySessionCompletionRecord,
} from "@/lib/types";
import { useTrainingDay } from "@/lib/use-training-day";

type HistoryTab = "sessions" | "exercises" | "sparring" | "checkins" | "injuries";

const TABS: Array<{ id: HistoryTab; label: string }> = [
  { id: "sessions", label: "Sessions" },
  { id: "exercises", label: "Exercises" },
  { id: "sparring", label: "Sparring" },
  { id: "checkins", label: "Check-ins" },
  { id: "injuries", label: "Injuries" },
];

type TabData<T> = {
  rows: T | null;
  error: string | null;
};

function StatusBadge({ tone, label }: { tone: string; label: string }) {
  return (
    <span className="badge history-status-badge" data-tone={tone}>
      {label}
    </span>
  );
}

function ListSkeleton() {
  return (
    <div className="history-list" aria-hidden="true">
      <Skeleton height={72} />
      <Skeleton height={72} />
      <Skeleton height={72} />
    </div>
  );
}

type SummaryStat = { label: string; value: number; tone?: TodayDecisionTone };

/** One labelled row of plain counts in a tab's at-a-glance card. */
function SummaryGroup({ label, stats }: { label: string; stats: SummaryStat[] }) {
  return (
    <div className="history-summary-group">
      <p className="history-summary-label">{label}</p>
      <dl
        className="history-summary-stats"
        style={{ "--stat-count": stats.length } as CSSProperties}
      >
        {stats.map((stat) => (
          <div key={stat.label}>
            <dt>{stat.label}</dt>
            <dd data-tone={stat.value > 0 && stat.tone !== "neutral" ? stat.tone : undefined}>
              {stat.value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/** The row's date, with "Today" / "Yesterday" / "N days ago" for the last week. */
function RowDate({ day, today }: { day: string; today: string | null }) {
  const ago = today ? trainingDaysAgo(day, today) : null;
  const when = ago !== null && ago < 7 ? daysAgoLabel(day, today ?? "") : null;
  return (
    <span>
      {formatAppDate(day)}
      {when ? <span className="history-row-when"> · {when}</span> : null}
    </span>
  );
}

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

function Chips({ chips }: { chips: HistoryChip[] }) {
  return (
    <div className="history-chips">
      {chips.map((chip) => (
        <span
          key={chip.label}
          className="history-chip"
          data-tone={chip.tone === "neutral" ? undefined : chip.tone}
        >
          {chip.label}
        </span>
      ))}
    </div>
  );
}

function SessionRows({ rows, today }: { rows: TodaySessionCompletionRecord[]; today: string | null }) {
  if (rows.length === 0) {
    return (
      <EmptyState
        eyebrow="Session history"
        title="No sessions logged yet."
        description="Every session you mark done, modified, or skipped on Today is recorded here with its RPE and reason."
        example="Thu 02 Jul 2026: Done · RPE 7/10"
        primaryAction={{ label: "Open Today", href: "/today" }}
      />
    );
  }
  const week = today
    ? countRecentBy(rows, { day: (row) => row.training_day, key: (row) => row.status, today, days: 7 })
    : null;
  return (
    <div className="history-tab-body">
      {week ? (
        <section className="history-summary" aria-label="Sessions in the last 7 days">
          <SummaryGroup
            label="Last 7 days"
            stats={[
              { label: "Done", value: week.done ?? 0, tone: "green" },
              { label: "Modified", value: week.modified ?? 0, tone: "amber" },
              { label: "Skipped", value: week.skipped ?? 0, tone: "red" },
            ]}
          />
        </section>
      ) : null}
      <ul className="history-list">
        {rows.map((row) => (
          <li key={row.id} className="history-row" data-tone={sessionStatusTone(row.status)}>
            <div className="history-row-head">
              <span className="history-row-title">{row.session_title?.trim() || "Session"}</span>
              <StatusBadge tone={sessionStatusTone(row.status)} label={sessionStatusLabel(row.status)} />
            </div>
            <div className="history-row-meta">
              <RowDate day={row.training_day} today={today} />
              {row.session_rpe != null ? (
                <span>
                  RPE {row.session_rpe}/10
                  <GlossaryTooltip term="RPE" />
                </span>
              ) : null}
              {row.pain_after != null ? <span>Pain after {row.pain_after}/10</span> : null}
            </div>
            {row.modification_reason ? (
              <p className="muted history-row-note">Reason: {row.modification_reason}</p>
            ) : null}
            {row.notes ? <p className="muted history-row-note">Notes: {row.notes}</p> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function SparringRows({ history }: { history: SparringLogHistoryResponse }) {
  const { logs, current_training_day: today } = history;
  if (logs.length === 0) {
    return (
      <EmptyState
        eyebrow="Sparring history"
        title="No sparring logged yet."
        description="Finish a sparring round timer on Today to log your rounds. They'll show here with weekly totals."
        example="Thu 02 Jul 2026: 5 × 3 min · Hard · Light head contact"
        primaryAction={{ label: "Open Today", href: "/today" }}
      />
    );
  }
  const week = history.last_7_days;
  const month = history.last_28_days;
  const weekNote = sparringWeekNote(week);
  const lastHard = history.last_hard_day ? daysAgoLabel(history.last_hard_day, today) : null;
  const lastRocked = history.last_rocked_day ? daysAgoLabel(history.last_rocked_day, today) : null;
  return (
    <div className="history-tab-body">
      <section className="history-summary" aria-label="Sparring totals">
        <SummaryGroup
          label="Last 7 days"
          stats={[
            { label: "Rounds", value: week.rounds },
            {
              label: "Hard days",
              value: week.hard_days,
              tone: week.hard_days > HARD_SPARRING_DAYS_PER_WEEK ? "amber" : undefined,
            },
            { label: "Heavy head contact", value: week.heavy_head_contact_sessions, tone: "amber" },
          ]}
        />
        <p className="history-summary-line">
          Last 28 days: {plural(month.sessions, "session")} · {plural(month.rounds, "round")} ·{" "}
          {plural(month.hard_days, "hard day")}
          {month.rocked_count > 0 ? (
            <span data-tone="red"> · rocked / dropped {plural(month.rocked_count, "time")}</span>
          ) : null}
        </p>
        <div className="history-row-meta">
          {history.last_hard_day ? (
            <span>
              Last hard spar: {formatAppDate(history.last_hard_day)}
              {lastHard ? ` (${lastHard})` : ""}
            </span>
          ) : null}
          {history.last_rocked_day ? (
            <span>
              Last rocked / dropped: {formatAppDate(history.last_rocked_day)}
              {lastRocked ? ` (${lastRocked})` : ""}
            </span>
          ) : null}
        </div>
        {weekNote ? (
          <p className="history-summary-note" role="note">
            {weekNote}
          </p>
        ) : null}
      </section>

      <ul className="history-list">
        {logs.map((row) => {
          const difference = sparringPlanDifference(row.planned_intensity, row.intensity);
          return (
            <li
              key={row.id}
              className="history-row"
              data-tone={row.rocked ? "red" : sparringIntensityTone(row.intensity)}
            >
              <div className="history-row-head">
                <span className="history-row-date">
                  <RowDate day={row.training_day} today={today} />
                </span>
                <StatusBadge
                  tone={sparringIntensityTone(row.intensity)}
                  label={sparringIntensityLabel(row.intensity)}
                />
              </div>
              <div className="history-row-meta">
                {sparringRowMeta(row).map((item) => (
                  <span key={item}>{item}</span>
                ))}
              </div>
              {row.rocked || row.head_contact === "heavy" || difference ? (
                <Chips
                  chips={[
                    ...(row.rocked ? [{ label: "Rocked / dropped", tone: "red" as const }] : []),
                    ...(row.head_contact === "heavy"
                      ? [{ label: "Heavy head contact", tone: "amber" as const }]
                      : []),
                    ...(difference
                      ? [{ label: difference.label, tone: difference.harder ? ("amber" as const) : ("neutral" as const) }]
                      : []),
                  ]}
                />
              ) : null}
              {row.notes ? <p className="muted history-row-note">Notes: {row.notes}</p> : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function CheckinRows({ rows, today }: { rows: TodayCheckinHistoryRecord[]; today: string | null }) {
  if (rows.length === 0) {
    return (
      <EmptyState
        eyebrow="Check-in history"
        title="No check-ins yet."
        description="Your daily readiness check-ins and the training recommendation each one produced appear here."
        example="Thu 02 Jul 2026: Train as planned · Sleep good · Body normal · Pain none"
        primaryAction={{ label: "Check in on Today", href: "/today" }}
      />
    );
  }
  const week = today
    ? countRecentBy(rows, {
        day: (row) => row.training_day,
        key: (row) => row.recommendation_state,
        today,
        days: 7,
      })
    : null;
  return (
    <div className="history-tab-body">
      {week ? (
        <section className="history-summary" aria-label="Check-ins in the last 7 days">
          <SummaryGroup
            label="Last 7 days"
            stats={[
              { label: "Train as planned", value: week.train_as_planned ?? 0, tone: "green" },
              { label: "Modify", value: week.modify ?? 0, tone: "amber" },
              { label: "Pull back", value: week.pull_back ?? 0, tone: "red" },
            ]}
          />
        </section>
      ) : null}
      <ul className="history-list">
        {rows.map((row) => (
          <li key={row.id} className="history-row" data-tone={recommendationTone(row.recommendation_state)}>
            <div className="history-row-head">
              <span className="history-row-date">
                <RowDate day={row.training_day} today={today} />
              </span>
              <StatusBadge
                tone={recommendationTone(row.recommendation_state)}
                label={recommendationLabel(row.recommendation_state)}
              />
            </div>
            <Chips chips={checkinChips(row)} />
            {row.recommendation_reason ? (
              <p className="muted history-row-note">{row.recommendation_reason.split("\n")[0]}</p>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function InjuryRow({ row }: { row: InjuryFlagRecord }) {
  const title = row.label || normalizeInjuryLabel(row.body_area) || row.description;
  // The stored description carries the planner's taxonomy tokens for a
  // guided-intake injury, so the note line shows only the athlete-facing
  // part of it.
  const note = formatInjuryDetail(row.description, { bodyArea: row.body_area });
  return (
    <li className="history-row" data-tone={injuryStatusTone(row.status)}>
      <div className="history-row-head">
        <span className="history-row-title">{title}</span>
        <StatusBadge tone={injuryStatusTone(row.status)} label={injuryStatusLabel(row.status)} />
      </div>
      <Chips
        chips={[
          {
            label: `${row.severity.charAt(0).toUpperCase()}${row.severity.slice(1)}`,
            tone: injurySeverityTone(row.severity),
          },
        ]}
      />
      <div className="history-row-meta">
        <span>Reported {formatAppDate(row.created_at)}</span>
        {row.resolved_at ? <span>Resolved {formatAppDate(row.resolved_at)}</span> : null}
        {!row.resolved_at && row.latest_reported_status ? (
          <span data-tone={injuryReportedTone(row.latest_reported_status)}>
            Latest: {row.latest_reported_status}
          </span>
        ) : null}
      </div>
      {note && note !== title ? <p className="muted history-row-note">{note}</p> : null}
    </li>
  );
}

function InjuryRows({ rows }: { rows: InjuryFlagRecord[] }) {
  if (rows.length === 0) {
    return (
      <EmptyState
        eyebrow="Injury history"
        title="No injuries reported."
        description="Injuries you report during check-ins stay here, including resolved ones, so you have your full injury record."
        example="Left knee: Moderate · Open since Mon 15 Jun 2026"
        primaryAction={{ label: "Report on Today", href: "/today" }}
      />
    );
  }
  const active = rows.filter((row) => row.status !== "resolved");
  const resolved = rows.filter((row) => row.status === "resolved");
  return (
    <div className="history-tab-body">
      <section className="history-summary" aria-label="Injuries">
        <SummaryGroup
          label="Injuries"
          stats={[
            { label: "Active", value: active.length, tone: "amber" },
            { label: "Resolved", value: resolved.length, tone: "green" },
          ]}
        />
      </section>
      {active.length > 0 ? (
        <>
          <h2 className="history-section-title">Active</h2>
          <ul className="history-list">
            {active.map((row) => (
              <InjuryRow key={row.id} row={row} />
            ))}
          </ul>
        </>
      ) : null}
      {resolved.length > 0 ? (
        <>
          <h2 className="history-section-title">Resolved</h2>
          <ul className="history-list">
            {resolved.map((row) => (
              <InjuryRow key={row.id} row={row} />
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}

function ExerciseRows({ history, onMore, loading }: {
  history: ExerciseHistoryResponse; onMore: () => void; loading: boolean;
}) {
  const [search, setSearch] = useState("");
  if (history.logs.length === 0) return <EmptyState eyebrow="Exercise history" title="No exercises logged yet."
    description="Your logged loads, sets and reps appear here across every plan." example="Log an exercise on Today to start your record." />;
  const rows = history.logs.filter((row) => String(row.prescribed.display_name ?? row.exercise_key ?? "")
    .toLowerCase().includes(search.trim().toLowerCase()));
  return <div className="history-tab-body">
    <label className="history-exercise-search">Find an exercise
      <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Exercise name" />
    </label>
    <ul className="history-list">
      {rows.map((row) => <li key={row.id} className="history-row" data-tone={row.status === "skipped" ? "grey" : "green"}>
        <div className="history-row-head">
          <span className="history-row-title">{String(row.prescribed.display_name ?? row.exercise_key ?? "Exercise")}</span>
          <StatusBadge tone={row.status === "skipped" ? "grey" : "green"} label={EXERCISE_LOG_STATUS_LABELS[row.status]} />
        </div>
        <div className="history-row-meta">{formatAppDate(row.training_day)}</div>
        <p className="history-summary-line">{performanceSummary(row)}</p>
        {row.reason ? <p className="muted history-row-note">{EXERCISE_LOG_REASON_LABELS[row.reason]}</p> : null}
      </li>)}
    </ul>
    {!rows.length ? <p className="muted">No matching exercises in the loaded history.</p> : null}
    {history.next_offset !== null ? <button className="secondary-button" disabled={loading} onClick={onMore}>
      {loading ? "Loading…" : "Load earlier records"}
    </button> : null}
  </div>;
}

export function HistoryScreen() {
  const { session } = useAppSession();
  return <HistoryContent key={session?.access_token ?? "anonymous"} />;
}

function HistoryContent() {
  const { session, me } = useAppSession();
  const token = session?.access_token ?? null;
  const userId = session?.user_id ?? null;
  // The training day for the "last 7 days" counts, in the athlete's own
  // timezone so it matches the server-stamped days on every row even when the
  // device is set elsewhere. useTrainingDay only supplies the client-only
  // mount gate and the minute tick that rolls the day over.
  const trainingDay = useTrainingDay();
  const today = trainingDay ? athleteTrainingDayISO(new Date(), me?.profile.athlete_timezone) : null;

  const [tab, setTab] = useState<HistoryTab>("sessions");
  const [sessions, setSessions] = useState<TabData<TodaySessionCompletionRecord[]>>({
    rows: null,
    error: null,
  });
  const [exercises, setExercises] = useState<TabData<ExerciseHistoryResponse>>({ rows: null, error: null });
  const [exerciseOffset, setExerciseOffset] = useState<number | null>(null);
  const [sparring, setSparring] = useState<TabData<SparringLogHistoryResponse>>({
    rows: null,
    error: null,
  });
  const [checkins, setCheckins] = useState<TabData<TodayCheckinHistoryRecord[]>>({
    rows: null,
    error: null,
  });
  const [injuries, setInjuries] = useState<TabData<InjuryFlagRecord[]>>({ rows: null, error: null });

  // Load each tab on first open, then retain its cache for this signed-in visit.
  // Retry clears the error and reopens the same effect. The keyed parent drops
  // every cache immediately when the account/token changes.
  useEffect(() => {
    if (!token) {
      return;
    }
    let cancelled = false;

    const load = async <T,>(
      current: TabData<T>,
      fetcher: (accessToken: string) => Promise<T>,
      set: (data: TabData<T>) => void,
    ) => {
      if (current.rows !== null || current.error !== null) {
        return;
      }
      try {
        const rows = await loadHistoryWithAuthRecovery(
          { access_token: token, user_id: userId },
          fetcher,
          () => cancelled,
        );
        if (!cancelled) {
          set({ rows, error: null });
        }
      } catch (error) {
        if (!cancelled) {
          set({ rows: null, error: error instanceof Error ? error.message : "Unable to load history." });
        }
      }
    };

    if (tab === "sessions") {
      void load(sessions, listSessionCompletionHistory, setSessions);
    } else if (tab === "exercises") {
      if (exerciseOffset !== null && exercises.rows) {
        const previous = exercises.rows;
        void load({ rows: null, error: null }, async (accessToken) => {
          const page = await listExerciseHistory(accessToken, exerciseOffset);
          return { ...page, logs: [...previous.logs, ...page.logs].filter((row, index, all) => all.findIndex((item) => item.id === row.id) === index) };
        }, (data) => { setExerciseOffset(null); setExercises(data.error ? { ...data, rows: previous } : data); });
      } else {
        void load(exercises, (accessToken) => listExerciseHistory(accessToken), setExercises);
      }
    } else if (tab === "sparring") {
      void load(sparring, listSparringLogHistory, setSparring);
    } else if (tab === "checkins") {
      void load(checkins, listTodayCheckinHistory, setCheckins);
    } else {
      void load(injuries, (accessToken) => listInjuryFlags(accessToken, true), setInjuries);
    }
    return () => {
      cancelled = true;
    };
  }, [tab, token, userId, sessions, exercises, exerciseOffset, sparring, checkins, injuries]);

  const active =
    tab === "sessions"
      ? sessions
      : tab === "exercises"
        ? exercises
      : tab === "sparring"
        ? sparring
        : tab === "checkins"
          ? checkins
          : injuries;

  return (
    <section className="panel history-screen">
      <header className="form-section-header">
        <p className="kicker">Training record</p>
        <h1 className="form-section-title">History</h1>
        <p className="muted">
          Your sessions, sparring, check-ins and injuries.
        </p>
      </header>

      <div className="history-tabs" role="tablist" aria-label="History sections">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            className={`history-tab${tab === item.id ? " history-tab-active" : ""}`}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {active.error ? (
        <div className="error-banner" role="alert">
          <p>{active.error}</p>
          <button
            type="button"
            className="error-banner-retry"
            onClick={() => {
              if (tab === "sessions") setSessions({ rows: null, error: null });
              else if (tab === "exercises") { setExerciseOffset(exercises.rows?.next_offset ?? null); setExercises((current) => ({ ...current, error: null })); }
              else if (tab === "sparring") setSparring({ rows: null, error: null });
              else if (tab === "checkins") setCheckins({ rows: null, error: null });
              else setInjuries({ rows: null, error: null });
            }}
          >
            Retry
          </button>
        </div>
      ) : active.rows === null ? (
        <ListSkeleton />
      ) : tab === "sessions" ? (
        <SessionRows rows={sessions.rows ?? []} today={today} />
      ) : tab === "exercises" ? (
        exercises.rows ? <ExerciseRows history={exercises.rows} loading={exerciseOffset !== null}
          onMore={() => setExerciseOffset(exercises.rows?.next_offset ?? null)} /> : <ListSkeleton />
      ) : tab === "sparring" ? (
        sparring.rows ? <SparringRows history={sparring.rows} /> : <ListSkeleton />
      ) : tab === "checkins" ? (
        <CheckinRows rows={checkins.rows ?? []} today={today} />
      ) : (
        <InjuryRows rows={injuries.rows ?? []} />
      )}
    </section>
  );
}
