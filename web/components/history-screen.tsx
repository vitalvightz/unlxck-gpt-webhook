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
import { formatAppDate } from "@/lib/date-format";
import {
  checkinFlagLabels,
  checkinSummary,
  daysAgoLabel,
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
import type {
  InjuryFlagRecord,
  SparringLogHistoryResponse,
  SparringWindowSummary,
  TodayCheckinHistoryRecord,
  TodaySessionCompletionRecord,
} from "@/lib/types";

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

function SessionRows({ rows }: { rows: TodaySessionCompletionRecord[] }) {
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
  return (
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
  );
}

function SparringWindow({ summary, label }: { summary: SparringWindowSummary; label: string }) {
  return (
    <div className="sparring-window">
      <p className="sparring-window-label">{label}</p>
      <dl className="sparring-window-stats">
        <div>
          <dt>Sessions</dt>
          <dd>{summary.sessions}</dd>
        </div>
        <div>
          <dt>Rounds</dt>
          <dd>{summary.rounds}</dd>
        </div>
        <div>
          <dt>Hard rounds</dt>
          <dd>{summary.hard_rounds}</dd>
        </div>
        <div>
          <dt>Hard days</dt>
          <dd>{summary.hard_days}</dd>
        </div>
        <div>
          <dt>Heavy head contact</dt>
          <dd>{summary.heavy_head_contact_sessions}</dd>
        </div>
        <div>
          <dt>Rocked / dropped</dt>
          <dd data-tone={summary.rocked_count > 0 ? "red" : undefined}>{summary.rocked_count}</dd>
        </div>
      </dl>
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
  const weekNote = sparringWeekNote(history.last_7_days);
  const lastHard = history.last_hard_day ? daysAgoLabel(history.last_hard_day, today) : null;
  const lastRocked = history.last_rocked_day ? daysAgoLabel(history.last_rocked_day, today) : null;
  return (
    <div className="sparring-history">
      <section className="sparring-summary" aria-label="Sparring totals">
        <SparringWindow summary={history.last_7_days} label="Last 7 days" />
        <SparringWindow summary={history.last_28_days} label="Last 28 days" />
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
          <p className="sparring-week-note" role="note">
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

function CheckinRows({ rows }: { rows: TodayCheckinHistoryRecord[] }) {
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
  return (
    <ul className="history-list">
      {rows.map((row) => {
        const flags = checkinFlagLabels(row);
        return (
          <li key={row.id} className="history-row">
            <div className="history-row-head">
              <span className="history-row-date">{formatAppDate(row.training_day)}</span>
              <StatusBadge
                tone={recommendationTone(row.recommendation_state)}
                label={recommendationLabel(row.recommendation_state)}
              />
            </div>
            <div className="history-row-meta">
              <span>{checkinSummary(row)}</span>
            </div>
            {flags.length > 0 ? (
              <p className="muted history-row-note">Flags: {flags.join(", ")}</p>
            ) : null}
            {row.recommendation_reason ? (
              <p className="muted history-row-note">{row.recommendation_reason.split("\n")[0]}</p>
            ) : null}
          </li>
        );
      })}
    </ul>
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
  return (
    <ul className="history-list">
      {rows.map((row) => {
        const title =
          row.label || normalizeInjuryLabel(row.body_area) || row.description;
        // The stored description carries the planner's taxonomy tokens for a
        // guided-intake injury, so the note line shows only the athlete-facing
        // part of it.
        const note = formatInjuryDetail(row.description, { bodyArea: row.body_area });
        return (
          <li key={row.id} className="history-row">
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
                <span>Latest: {row.latest_reported_status}</span>
              ) : null}
            </div>
            {note && note !== title ? (
              <p className="muted history-row-note">{note}</p>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

export function HistoryScreen() {
  const { session } = useAppSession();
  const token = session?.access_token ?? null;

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
        <SessionRows rows={sessions.rows ?? []} />
      ) : tab === "sparring" ? (
        sparring.rows ? <SparringRows history={sparring.rows} /> : <ListSkeleton />
      ) : tab === "checkins" ? (
        <CheckinRows rows={checkins.rows ?? []} />
      ) : (
        <InjuryRows rows={injuries.rows ?? []} />
      )}
    </section>
  );
}
