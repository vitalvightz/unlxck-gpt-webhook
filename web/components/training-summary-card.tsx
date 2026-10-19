"use client";

import { type CSSProperties, type ReactNode, useEffect, useState } from "react";

import { formatTrainingDuration, summarizeTraining, summaryWindowLoaded } from "@/lib/training-summary";
import type { TrainingHistorySession } from "@/lib/training-history";
import styles from "./training-summary.module.css";

const WINDOWS = [
  { days: 7, label: "Last 7 days", empty: "No training logged in the last 7 days." },
  { days: 28, label: "Last 4 weeks", empty: "No training logged in the last 4 weeks." },
] as const;

/**
 * How training is trending: volume and mix over a recent window, from logged
 * records only. Totals show only once every session in the window is loaded;
 * until then the card loads the missing pages instead of undercounting.
 */
export function TrainingSummaryCard({ rows, today, loadedFrom, loading, error, onLoadMore, children }: {
  rows: readonly TrainingHistorySession[]; today: string;
  /** Oldest training day whose sessions are all loaded; null once History is fully loaded. */
  loadedFrom: string | null;
  loading: boolean; error: string | null; onLoadMore: () => Promise<void>;
  children?: ReactNode;
}) {
  const [days, setDays] = useState<7 | 28>(7);
  const window = WINDOWS.find(item => item.days === days)!;
  const complete = summaryWindowLoaded(loadedFrom, today, days);
  const summary = summarizeTraining(rows, today, days);
  useEffect(() => {
    if (!complete && !loading && !error) void onLoadMore();
  }, [complete, loading, error, onLoadMore]);
  const longest = Math.max(1, ...summary.mix.map(row => row.minutes));
  return (
    <section className={`history-summary ${styles.card}`} aria-label="Training summary">
      <div className={styles.head}>
        <p className="history-summary-label">Your training</p>
        <div className={styles.toggle} role="group" aria-label="Summary window">
          {WINDOWS.map(item => (
            <button key={item.days} type="button" aria-pressed={days === item.days} onClick={() => setDays(item.days)}>
              {item.label}
            </button>
          ))}
        </div>
      </div>
      {!complete ? error ? (
        <div className={styles.incomplete} role="alert">
          <p>Not every session from this period loaded, so totals aren&apos;t shown.</p>
          <button type="button" className="secondary-button" onClick={() => void onLoadMore()}>Retry</button>
        </div>
      ) : <p className="muted history-row-note" role="status">Loading every session in this period…</p>
      : summary.sessions === 0 ? <p className="muted history-row-note">{window.empty}</p> : <>
        <dl className={`history-summary-stats ${styles.stats}`} style={{ "--stat-count": 3 } as CSSProperties}>
          <div><dt>Sessions</dt><dd>{summary.sessions}</dd></div>
          <div><dt>Training</dt><dd>{formatTrainingDuration(summary.minutes)}</dd></div>
          <div><dt>{summary.mix.length === 1 ? "Discipline" : "Disciplines"}</dt><dd>{summary.mix.length}</dd></div>
        </dl>
        <div className={styles.mix}>
          <p className={styles.mixTitle}>Training mix</p>
          <ul aria-label="Minutes by discipline">
            {summary.mix.map((row, index) => (
              <li key={row.key}>
                <span className={styles.mixLabel}>{row.label}</span>
                <span className={styles.track} aria-hidden="true">
                  <span className={styles.bar} data-lead={index === 0 && row.minutes > 0 ? "" : undefined}
                    style={{ "--share": `${(row.minutes / longest) * 100}%` } as CSSProperties} />
                </span>
                <span className={styles.mixValue}>
                  {row.minutes ? `${row.minutes}m` : `${row.sessions} ${row.sessions === 1 ? "session" : "sessions"}`}
                </span>
              </li>
            ))}
          </ul>
          {summary.untimed ? (
            <p className={styles.footnote}>
              {summary.untimed} {summary.untimed === 1 ? "session has" : "sessions have"} no recorded duration and {summary.untimed === 1 ? "isn't" : "aren't"} in the time total.
            </p>
          ) : null}
        </div>
      </>}
      {children}
    </section>
  );
}
