"use client";

import { useEffect, useState } from "react";

import { useAppSession } from "@/components/auth-provider";
import { EmptyState } from "@/components/empty-state";
import { GlossaryTooltip } from "@/components/glossary-tooltip";
import { Skeleton } from "@/components/skeleton";
import {
  listInjuryFlags,
  listSessionCompletionHistory,
  listSparringLogHistory,
  listTodayCheckinHistory,
} from "@/lib/api";
import { toISODate } from "@/lib/camp-map";
import { formatAppDate } from "@/lib/date-format";
import {
  checkinChips,
  countRecentBy,
  daysAgoLabel,
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
} from "@/lib/history";
import { formatInjuryDetail, normalizeInjuryLabel } from "@/lib/injury-display";
import type { TodayDecisionTone } from "@/lib/today";
import type {
  InjuryFlagRecord,
  SparringLogHistoryResponse,
  SparringWindowSummary,
  TodayCheckinHistoryRecord,
  TodaySessionCompletionRecord,
} from "@/lib/types";
import { useTrainingDay } from "@/lib/use-training-day";

type HistoryTab = "sessions" | "sparring" | "checkins" | "injuries";

const TABS: Array<{ id: HistoryTab; label: string }> = [
  { id: "sessions", label: "Sessions" },
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
      <dl className="history-summary-stats">
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
        example="Thu 02 Jul 2026 — Done · RPE 7/10"
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
          <li key={row.id} className="history-row">
            <div className="history-row-head">
              <span className="history-row-title">{row.session_title?.trim() || "Session"}</span>
              <StatusBadge tone={sessionStatusTone(row.status)} label={sessionStatusLabel(row.status)} />
            </div>
            <div className="history-row-meta">
              <span>{formatAppDate(row.training_day)}</span>
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
        description="When a sparring round timer on Today finishes, log how it went in a few taps. Every entry — rounds, intensity, head contact — is kept here with your weekly totals."
        example="Thu 02 Jul 2026 — 5 × 3 min · Hard · Light head contact"
        primaryAction={{ label: "Open Today", href: "/today" }}
      />
    );
  }
  const windowStats = (summary: SparringWindowSummary): SummaryStat[] => [
    { label: "Sessions", value: summary.sessions },
    { label: "Rounds", value: summary.rounds },
    { label: "Hard rounds", value: summary.hard_rounds },
    { label: "Hard days", value: summary.hard_days },
    { label: "Heavy head contact", value: summary.heavy_head_contact_sessions },
    { label: "Rocked / dropped", value: summary.rocked_count, tone: "red" },
  ];
  const weekNote = sparringWeekNote(history.last_7_days);
  const lastHard = history.last_hard_day ? daysAgoLabel(history.last_hard_day, today) : null;
  const lastRocked = history.last_rocked_day ? daysAgoLabel(history.last_rocked_day, today) : null;
  return (
    <div className="history-tab-body">
      <section className="history-summary" aria-label="Sparring totals">
        <SummaryGroup label="Last 7 days" stats={windowStats(history.last_7_days)} />
        <SummaryGroup label="Last 28 days" stats={windowStats(history.last_28_days)} />
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
            <li key={row.id} className="history-row">
              <div className="history-row-head">
                <span className="history-row-date">{formatAppDate(row.training_day)}</span>
                <span className="history-badges">
                  <StatusBadge
                    tone={sparringIntensityTone(row.intensity)}
                    label={sparringIntensityLabel(row.intensity)}
                  />
                  {row.head_contact === "heavy" ? (
                    <StatusBadge tone="amber" label="Heavy head contact" />
                  ) : null}
                  {row.rocked ? <StatusBadge tone="red" label="Rocked / dropped" /> : null}
                </span>
              </div>
              <div className="history-row-meta">
                {sparringRowMeta(row).map((item) => (
                  <span key={item}>{item}</span>
                ))}
                {difference ? (
                  <span data-tone={difference.harder ? "amber" : undefined}>{difference.label}</span>
                ) : null}
              </div>
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
        example="Thu 02 Jul 2026 — Train as planned · Sleep good · Body normal · Pain none"
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
          <li key={row.id} className="history-row">
            <div className="history-row-head">
              <span className="history-row-date">{formatAppDate(row.training_day)}</span>
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
    <li className="history-row">
      <div className="history-row-head">
        <span className="history-row-date">{title}</span>
        <span className="history-badges">
          <StatusBadge tone={injurySeverityTone(row.severity)} label={row.severity} />
          <StatusBadge tone={injuryStatusTone(row.status)} label={injuryStatusLabel(row.status)} />
        </span>
      </div>
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
        description="Injuries you report during check-ins stay here — including resolved ones — so your full injury record is auditable."
        example="Left knee — Moderate · Open since Mon 15 Jun 2026"
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

export function HistoryScreen() {
  const { session } = useAppSession();
  const token = session?.access_token ?? null;
  // The athlete-local training day for the "last 7 days" counts (client-only,
  // null until mount so server and first client render match).
  const trainingDay = useTrainingDay();
  const today = trainingDay ? toISODate(trainingDay) : null;

  const [tab, setTab] = useState<HistoryTab>("sessions");
  const [sessions, setSessions] = useState<TabData<TodaySessionCompletionRecord[]>>({
    rows: null,
    error: null,
  });
  const [sparring, setSparring] = useState<TabData<SparringLogHistoryResponse>>({
    rows: null,
    error: null,
  });
  const [checkins, setCheckins] = useState<TabData<TodayCheckinHistoryRecord[]>>({
    rows: null,
    error: null,
  });
  const [injuries, setInjuries] = useState<TabData<InjuryFlagRecord[]>>({ rows: null, error: null });

  // The cache is keyed to the signed-in token: if it changes (sign-out /
  // different account), drop every tab so one user's history can never be
  // shown to another.
  useEffect(() => {
    setSessions({ rows: null, error: null });
    setSparring({ rows: null, error: null });
    setCheckins({ rows: null, error: null });
    setInjuries({ rows: null, error: null });
  }, [token]);

  // Lazy per-tab fetch: each tab loads on first open and is cached for the
  // rest of the visit. The tab states are dependencies on purpose: the
  // token-change reset above lands one render later than this effect's first
  // pass, so the effect must re-run when a cache flips back to null or the
  // reset would strand the tab on its loading skeleton forever. A tab that
  // already has rows or an error is left alone, so this cannot loop.
  useEffect(() => {
    if (!token) {
      return;
    }
    let cancelled = false;

    const load = async <T,>(
      current: TabData<T>,
      fetcher: () => Promise<T>,
      set: (data: TabData<T>) => void,
    ) => {
      if (current.rows !== null || current.error !== null) {
        return;
      }
      try {
        const rows = await fetcher();
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
      void load(sessions, () => listSessionCompletionHistory(token), setSessions);
    } else if (tab === "sparring") {
      void load(sparring, () => listSparringLogHistory(token), setSparring);
    } else if (tab === "checkins") {
      void load(checkins, () => listTodayCheckinHistory(token), setCheckins);
    } else {
      void load(injuries, () => listInjuryFlags(token, true), setInjuries);
    }
    return () => {
      cancelled = true;
    };
  }, [tab, token, sessions, sparring, checkins, injuries]);

  const active =
    tab === "sessions"
      ? sessions
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
          Every logged session, sparring round, daily check-in, and injury report — including
          resolved injuries.
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
          {active.error}
        </div>
      ) : active.rows === null ? (
        <ListSkeleton />
      ) : tab === "sessions" ? (
        <SessionRows rows={sessions.rows ?? []} today={today} />
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
