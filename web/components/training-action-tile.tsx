import styles from "./training-action-tile.module.css";

/** Shared visual anatomy; each action keeps its own navigation or form logic. */
export function TrainingActionContent({ kind }: { kind: "log" | "find" }) {
  return <>
    <span className={styles.icon} aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
        {kind === "log" ? <path d="M12 5v14M5 12h14" /> : <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></>}
      </svg>
    </span>
    <span className={styles.copy}><strong>{kind === "log" ? "Log session" : "Find a Drill"}</strong>
      <span>{kind === "log" ? "Log your own session." : "Explore the library."}</span>
    </span>
    <svg className={styles.chevron} viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 7 7-7 7" /></svg>
  </>;
}
