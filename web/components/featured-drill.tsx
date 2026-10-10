"use client";

import { useEffect, useState } from "react";
import { getFeaturedDrill } from "@/lib/api";
import type { LibraryEntry } from "@/lib/api-schema.generated";
import { ExerciseDemo } from "./exercise-demo";
import { DrillPreview } from "./training-library";
import styles from "./plans/plans.module.css";

export function FeaturedDrill({ accessToken }: { accessToken: string | null }) {
  // A refreshed account/token gets fresh data and cannot retain another user's preview.
  return accessToken ? <FeaturedDrillContent key={accessToken} token={accessToken} /> : null;
}

function FeaturedDrillContent({ token }: { token: string }) {
  const [entry, setEntry] = useState<LibraryEntry | null>(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void getFeaturedDrill(token, controller.signal).then(result => {
      if (!controller.signal.aborted) setEntry(result.entry?.media ? result.entry : null);
    }).catch(() => { /* Optional discovery never blocks the athlete's plan. */ });
    return () => controller.abort();
  }, [token]);
  if (!entry?.media) return null;
  return <section className={styles.featured} aria-label="Featured drill">
    <div className={styles.sectionHead}><h2 className={styles.sectionTitle}>Featured drill</h2>
      <span className={styles.sectionMeta}>Editor’s pick</span></div>
    <ExerciseDemo media={entry.media} exerciseName={entry.name} />
    <button className={styles.featuredDetails} onClick={() => setOpen(true)} aria-haspopup="dialog">
      <span className={styles.rowText}><strong className={styles.rowTitle}>{entry.name}</strong>
        <span className={styles.rowMeta}>{entry.equipment === null ? "Equipment unspecified" : entry.equipment.length ? entry.equipment.map(value => value.replaceAll("_", " ")).join(" · ") : "No equipment"}</span></span>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 7 7-7 7" /></svg>
    </button>
    {open ? <DrillPreview entry={entry} token={token} onClose={() => setOpen(false)} /> : null}
  </section>;
}
