"use client";

import { type CSSProperties, useState } from "react";

import { formatTrainingDuration, summarizeTraining } from "@/lib/training-summary";
import type { TrainingHistorySession } from "@/lib/training-history";
import styles from "./training-summary.module.css";

const WINDOWS = [
  { days: 7, label: "This week", empty: "No training logged in the last 7 days." },
  { days: 28, label: "Last 4 weeks", empty: "No training logged in the last 4 weeks." },
] as const;

/** How training is trending: volume and mix over a recent window, from logged records only. */
export function TrainingSummaryCard({ rows, today }: { rows: readonly TrainingHistorySession[]; today: string }) {
  const [days, setDays] = useState<7 | 28>(7);
  const window = WINDOWS.find(item => item.days === days)!;
  const summary = summarizeTraining(rows, today, days);
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
      {summary.sessions === 0 ? <p className="muted history-row-note">{window.empty}</p> : <>
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
    </section>
  );
}
