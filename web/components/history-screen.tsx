"use client";

import { useEffect, useState } from "react";

import { useAppSession } from "@/components/auth-provider";
import { EmptyState } from "@/components/empty-state";
import { GlossaryTooltip } from "@/components/glossary-tooltip";
import { Skeleton } from "@/components/skeleton";
import {
  listInjuryFlags,
  listSessionCompletionHistory,
  listTodayCheckinHistory,
} from "@/lib/api";
import { formatAppDate } from "@/lib/date-format";
import {
  checkinFlagLabels,
  checkinSummary,
  injurySeverityTone,
  injuryStatusLabel,
  injuryStatusTone,
  recommendationLabel,
  recommendationTone,
  sessionStatusLabel,
  sessionStatusTone,
} from "@/lib/history";
import { formatInjuryDetail, normalizeInjuryLabel } from "@/lib/injury-display";
import type {

  InjuryFlagRecord,
  TodayCheckinHistoryRecord,
  TodaySessionCompletionRecord,
} from "@/lib/types";
import { useTranslations as useAppTranslations } from "next-intl";

type HistoryTab = "sessions" | "checkins" | "injuries";

const TABS: Array<{ id: HistoryTab; label: string }> = [
  { id: "sessions", label: "Sessions" },
  { id: "checkins", label: "Check-ins" },
  { id: "injuries", label: "Injuries" },
];

type TabData<T> = {
  rows: T[] | null;
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
    const appText = useAppTranslations("AppText");
  if (rows.length === 0) {
    return (
      <EmptyState
        eyebrow={appText("text_c1c80b037867")}
        title={appText("text_612e14b1712f")}
        description={appText("text_34ee5d207ab5")}
        example={appText("text_1aa03009d120")}
        primaryAction={{ label: "Open Today", href: "/today" }}
      />
    );
  }
  return (
    <ul className="history-list">
      {rows.map((row) => (
        <li key={row.id} className="history-row">
          <div className="history-row-head">
            <span className="history-row-date">{formatAppDate(row.training_day)}</span>
            <StatusBadge tone={sessionStatusTone(row.status)} label={sessionStatusLabel(row.status)} />
          </div>
          <div className="history-row-meta">
            {row.session_rpe != null ? (
              <span>
                {appText("text_3a95f8f4dddd")}{row.session_rpe}{appText("text_00970dc27263")}<GlossaryTooltip term={appText("text_3a95f8f4dddd")} />
              </span>
            ) : null}
            {row.pain_after != null ? <span>{appText("text_ff3440ed93c4")}{row.pain_after}{appText("text_00970dc27263")}</span> : null}
          </div>
          {row.modification_reason ? (
            <p className="muted history-row-note">{appText("text_3425d1086921")}{row.modification_reason}</p>
          ) : null}
          {row.notes ? <p className="muted history-row-note">{appText("text_da4f7ea58d96")}{row.notes}</p> : null}
        </li>
      ))}
    </ul>
  );
}

function CheckinRows({ rows }: { rows: TodayCheckinHistoryRecord[] }) {
    const appText = useAppTranslations("AppText");
  if (rows.length === 0) {
    return (
      <EmptyState
        eyebrow={appText("text_7fb8eca7cfd4")}
        title={appText("text_84c28deeba54")}
        description={appText("text_b8fcb3285cee")}
        example={appText("text_6a220d58f6f2")}
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
              <p className="muted history-row-note">{appText("text_2df88939ccfe")}{flags.join(", ")}</p>
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
    const appText = useAppTranslations("AppText");
  if (rows.length === 0) {
    return (
      <EmptyState
        eyebrow={appText("text_fae2bbe2970a")}
        title={appText("text_c79cc4bc220d")}
        description={appText("text_a6e277549e9d")}
        example={appText("text_348a07bd2ff4")}
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
              <span>{appText("text_34540bb7b089")}{formatAppDate(row.created_at)}</span>
              {row.resolved_at ? <span>{appText("text_5be3c2c8354e")}{formatAppDate(row.resolved_at)}</span> : null}
              {!row.resolved_at && row.latest_reported_status ? (
                <span>{appText("text_983fbfe22297")}{row.latest_reported_status}</span>
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
    const appText = useAppTranslations("AppText");
  const { session } = useAppSession();
  const token = session?.access_token ?? null;

  const [tab, setTab] = useState<HistoryTab>("sessions");
  const [sessions, setSessions] = useState<TabData<TodaySessionCompletionRecord>>({
    rows: null,
    error: null,
  });
  const [checkins, setCheckins] = useState<TabData<TodayCheckinHistoryRecord>>({
    rows: null,
    error: null,
  });
  const [injuries, setInjuries] = useState<TabData<InjuryFlagRecord>>({ rows: null, error: null });

  // The cache is keyed to the signed-in token: if it changes (sign-out /
  // different account), drop every tab so one user's history can never be
  // shown to another.
  useEffect(() => {
    setSessions({ rows: null, error: null });
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
      fetcher: () => Promise<T[]>,
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
    } else if (tab === "checkins") {
      void load(checkins, () => listTodayCheckinHistory(token), setCheckins);
    } else {
      void load(injuries, () => listInjuryFlags(token, true), setInjuries);
    }
    return () => {
      cancelled = true;
    };
  }, [tab, token, sessions, checkins, injuries]);

  const active =
    tab === "sessions" ? sessions : tab === "checkins" ? checkins : injuries;

  return (
    <section className="panel history-screen">
      <header className="form-section-header">
        <p className="kicker">{appText("text_095eea84c2cd")}</p>
        <h1 className="form-section-title">{appText("text_0e7696009337")}</h1>
        <p className="muted">
          {appText("text_ecf003cec6c3")}</p>
      </header>

      <div className="history-tabs" role="tablist" aria-label={appText("text_ec0498815374")}>
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
      ) : tab === "checkins" ? (
        <CheckinRows rows={checkins.rows ?? []} />
      ) : (
        <InjuryRows rows={injuries.rows ?? []} />
      )}
    </section>
  );
}
