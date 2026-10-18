import Link from "next/link";
import { formatAppDate } from "@/lib/date-format";
import { sortTrainingHistory, type TrainingHistorySession } from "@/lib/training-history";
import styles from "./tracking-today.module.css";

export function TrackingHistoryPreview({ history, loading, error, onRetry }: {
  history: TrainingHistorySession[]; loading: boolean; error: boolean; onRetry: () => void;
}) {
  const recent = sortTrainingHistory(history).slice(0, 3);
  return <>
    <Link href="/timer" className={styles.tool}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 3h4M12 9v4l2 1M18 6l1-1" /><circle cx="12" cy="14" r="7" /></svg>
      <span><strong>Round timer</strong><span>Start a session</span></span><span aria-hidden="true">↗</span>
    </Link>
    <section className={styles.history} aria-labelledby="tracking-history-heading" aria-busy={loading}>
      <header><h2 id="tracking-history-heading">Training history</h2><Link href="/history">View all <span aria-hidden="true">→</span></Link></header>
      {error ? <div className={styles.empty} role="status"><p>Couldn’t load your training history.</p><button type="button" className="ghost-button" onClick={onRetry}>Retry history</button></div>
        : loading ? <p className={styles.empty} role="status">Loading training history…</p>
          : recent.length ? <ul className={styles.sessions}>{recent.map(row => <li key={`${row.source}-${row.id}`}>
            <div><strong>{row.title}</strong><span>{formatAppDate(row.training_day)}{row.duration_minutes ? ` · ${row.duration_minutes} min` : ""}</span></div>
            <span className={styles.source}>{row.source === "external" ? "Logged" : "UNLXCK"}</span>
          </li>)}</ul>
            : <div className={styles.empty}><strong>No training logged yet</strong><p>Your sessions will appear here once recorded.</p></div>}
    </section>
    <Link href="/quick-build" className={styles.plan}><span><strong>Want extra S&amp;C?</strong><span>Build a plan around your training.</span></span><span aria-hidden="true">↗</span></Link>
  </>;
}
