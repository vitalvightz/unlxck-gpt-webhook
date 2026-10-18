"use client";

import { TrainingHabitLog } from "./training-habit-log";
import { formatTrainingDay } from "./today/format";
import type { TodayCommandView } from "@/lib/types";
import styles from "./tracking-today.module.css";

export function TrackingToday({ accessToken, state, onSaved }: {
  accessToken: string | null; state: TodayCommandView | null; onSaved: () => void;
}) {
  return <section className={styles.root} aria-labelledby="tracking-today-heading">
    <header className={styles.header}><p>{formatTrainingDay(state?.today.training_day)}</p><h1 id="tracking-today-heading">Today</h1></header>
    <div className={styles.intro}><h2>Your training, your record.</h2><p>Log sessions from your coach or your own training.</p></div>
    <TrainingHabitLog accessToken={accessToken} state={state} onSaved={onSaved} trackingFirst />
  </section>;
}
