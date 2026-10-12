"use client";

import Link from "next/link";

import styles from "./home.module.css";
import { SummaryChipList } from "@/components/today/summary-chips";
import { useXp } from "@/components/xp-provider";
import { getDays, getSessions, getWeeks } from "@/lib/structured-plan";
import { openBlockWeekIntent } from "@/lib/open-block";
import { shortSessionType, type SummaryChip } from "@/lib/session-summary";
import type { RehabLabelPolicy, StructuredPlan, TodayCommandView } from "@/lib/types";

// Home: where the athlete is (fight countdown or current block), what comes
// next, their momentum, and anything to watch. Today owns the doing.

/** No fight date is a complete way to train, not a missing plan: the athlete
 * is in a renewable block, so Home leads with where they are in it. */
export function CurrentBlockCard({
  plan,
  weekNumber,
  trainingDay,
  policy,
}: {
  plan: StructuredPlan | null;
  weekNumber: number | null;
  trainingDay: Date | null;
  policy?: RehabLabelPolicy | null;
}) {
  const weeks = getWeeks(plan);
  const weekCount = weeks.length || 4;
  const intent = weekNumber ? openBlockWeekIntent(weekNumber) : null;
  const week = weekNumber ? weeks[weekNumber - 1] : null;
  const focus = Array.from(
    new Set(
      getDays(week)
        .flatMap((day) => getSessions(day))
        .filter((session) => !session.optional)
        .map((session) => shortSessionType(session, policy))
        .filter(Boolean),
    ),
  ).slice(0, 3);
  // Monday-based day of the week, so the bar moves day by day through the block.
  const weekday = trainingDay ? ((trainingDay.getDay() + 6) % 7) + 1 : 1;
  const pct = weekNumber ? Math.min(100, Math.round((((weekNumber - 1) * 7 + weekday) / (weekCount * 7)) * 100)) : null;

  return (
    <section className="fight-countdown" aria-label="Current block">
      <div className="fight-countdown-head">
        <div>
          <p className="fight-countdown-kicker">Current block</p>
          <p className="fight-countdown-days">
            <span className={styles.blockTitle}>{weekCount}-week training block</span>
          </p>
          {focus.length ? <p className="fight-countdown-date">{focus.join(" · ")}</p> : null}
        </div>
        {weekNumber ? (
          <span className="fight-countdown-meta">
            Week {weekNumber} of {weekCount}
            {intent ? ` · ${intent.label}` : ""}
          </span>
        ) : null}
      </div>
      {pct !== null ? (
        <div
          className="overview-progress-track fight-countdown-track"
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Block progress"
        >
          <span className={`overview-progress-fill ${styles.blockFill}`} style={{ width: `${pct}%` }} />
        </div>
      ) : null}
      {intent ? (
        <p className="fight-countdown-next">
          <span className="fight-countdown-next-label">This week</span> {intent.summary}
        </p>
      ) : null}
    </section>
  );
}

export type UpNextDecision = {
  /** GO / ADJUST / STOP / CHECK / PREVIEW, as Today shows it. */
  chip: string;
  tone?: "green" | "amber" | "red";
  line: string;
};

/** The next session in one card, with today's call on it and one way in. */
export function UpNextCard({
  dateLabel,
  title,
  subtitle,
  chips,
  decision,
  action,
}: {
  dateLabel: string;
  title: string;
  subtitle?: string;
  chips: SummaryChip[];
  decision?: UpNextDecision | null;
  action: { href: string; label: string };
}) {
  return (
    <section className={styles.section} aria-labelledby="home-up-next">
      <div className={styles.sectionHead}>
        <h2 id="home-up-next" className={styles.sectionTitle}>Up next</h2>
        {dateLabel ? <span className={styles.sectionMeta}>{dateLabel}</span> : null}
      </div>
      <article className={`status-card overview-command-card ${styles.card}`} data-tone={decision?.tone}>
        <p className={styles.cardTitle}>{title}</p>
        {subtitle ? <p className={styles.cardSubtitle}>{subtitle}</p> : null}
        {chips.length ? <SummaryChipList chips={chips} /> : null}
        {decision ? (
          <p className={styles.decision} data-tone={decision.tone}>
            <span className={styles.decisionChip}>{decision.chip}</span>
            {decision.line}
          </p>
        ) : null}
        <Link href={action.href} className={`cta overview-primary-action ${styles.action}`}>
          {action.label} <span aria-hidden="true">→</span>
        </Link>
      </article>
    </section>
  );
}

/** This week's planned sessions done so far, from the same weekly record the
 * XP week bonus uses. Hidden when there is no current week to count. */
export function ThisWeekCard() {
  const xp = useXp();
  const week = xp.isHydrated ? xp.progress.currentWeek : null;
  if (!week || week.plannedSessions <= 0) return null;
  const done = Math.min(week.completedSessions, week.plannedSessions);
  const remaining = Math.max(0, week.plannedSessions - done);
  return (
    <section className={styles.section} aria-labelledby="home-this-week">
      <div className={styles.sectionHead}>
        <h2 id="home-this-week" className={styles.sectionTitle}>This week</h2>
      </div>
      <div className={`status-card ${styles.card}`}>
        <p className={styles.weekCount}>
          <span className={styles.weekNumber}>
            {done}/{week.plannedSessions}
          </span>{" "}
          sessions completed
        </p>
        <div className={styles.segments} aria-hidden="true">
          {Array.from({ length: week.plannedSessions }, (_, index) => (
            <span key={index} data-done={index < done || undefined} />
          ))}
        </div>
        <p className={styles.heroMeta}>
          {week.complete || remaining === 0
            ? "Week complete."
            : `${remaining} ${remaining === 1 ? "session" : "sessions"} remaining this week`}
        </p>
      </div>
    </section>
  );
}

/** Anything to watch, in one line; Today holds the detail. */
export function TrainingAlertsRow({ state }: { state: TodayCommandView | null }) {
  const injuries = state?.open_injuries?.length ?? 0;
  const risks = state?.risk_watch?.length ?? 0;
  if (!injuries && !risks) return null;
  const summary = injuries
    ? `${injuries} ${injuries === 1 ? "injury" : "injuries"} being monitored`
    : `${risks} ${risks === 1 ? "alert" : "alerts"} to review`;
  return (
    <Link href={injuries ? "/today#today-injury" : "/today"} className={`status-card ${styles.alertRow}`}>
      <span className={styles.alertText}>
        <span className={styles.sectionTitle}>Training alerts</span>
        <span className={styles.sectionMeta}>{summary}</span>
      </span>
      <span className={styles.chevron} aria-hidden="true" />
    </Link>
  );
}
