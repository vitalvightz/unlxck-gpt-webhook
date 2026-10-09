"use client";

import Link from "next/link";
import { useMemo } from "react";
import styles from "./today-screen.module.css";

import { useAppSession } from "@/components/auth-provider";
import { hasHealthDataConsent } from "@/lib/compliance";
import { ContextualFeedback } from "@/components/feedback/contextual-feedback";
import { Skeleton } from "@/components/skeleton";
import { formatTrainingDay } from "@/components/today/format";
import { TodayDecisionPanel } from "@/components/today/today-decision-panel";
import { TodayInjuryManager } from "@/components/today/today-injury-manager";
import { TodayReadinessForm } from "@/components/today/today-readiness-form";
import { TodayRiskWatch } from "@/components/today/today-risk-watch";
import { TodaySessionPanel } from "@/components/today/today-session-panel";
import { useTodayCommand } from "@/components/today/use-today-command";
import { humanizeIfRawEnum } from "@/lib/plan-labels";
import { isOpenOngoingPlan } from "@/lib/plan-format";
import { getTodayNextStep } from "@/lib/today-next-step";
import {
  TODAY_EMPTY_TEXT,
  TODAY_EMPTY_TITLE,
  getCompletionLabel,
  getDistinctTodayRiskWatch,
  getSupplementaryRiskWatch,
  hasActivePlan,
  resolveTodayDecision,
  shouldShowTodayCheckin,
} from "@/lib/today";
import type { TodayCompletionStatus } from "@/lib/types";

function TodayLoadingState() {
  return (
    <section className="panel today-shell" aria-busy="true">
      <Skeleton variant="text" width={120} />
      <Skeleton variant="text" width="70%" height={42} />
      <Skeleton variant="block" height={180} />
      <Skeleton variant="block" height={220} />
    </section>
  );
}

function NoActivePlanState() {
  return (
    <section className="panel today-shell today-empty-state">
      <div className="today-hero-copy">
        <p className="kicker">Today</p>
        <h1>{TODAY_EMPTY_TITLE}</h1>
        <p className="muted">{TODAY_EMPTY_TEXT}</p>
      </div>
      <div className="today-action-row">
        <Link href="/onboarding" className="cta">
          Complete Intake
        </Link>
        <Link href="/timer" className="secondary-button">
          Round timer
        </Link>
      </div>
    </section>
  );
}

type TileIconName = "check" | "clock" | "pulse" | "injury" | "plan" | "history" | "timer";

const TILE_ICON_PATHS: Record<TileIconName, string> = {
  check: "M7 12.5l3.2 3.2L17 9",
  clock: "M12 7.5V12l3 2",
  pulse: "M5 12h3l2-4 4 8 2-4h3",
  injury: "M12 7v6M12 16.5v.5",
  plan: "M7 7h10M7 12h10M7 17h6",
  history: "M5 12a7 7 0 107-7 7 7 0 00-5 2.1M5 5v3h3M12 8.5V12l2.5 1.5",
  timer: "M12 13V9.5M9.5 3h5M12 21a8 8 0 100-16 8 8 0 000 16z",
};

function TileIcon({ name, ring = false }: { name: TileIconName; ring?: boolean }) {
  return (
    <svg className={styles.icon} viewBox="0 0 24 24" aria-hidden="true">
      <g fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        {ring ? <circle cx="12" cy="12" r="10" /> : null}
        <path d={TILE_ICON_PATHS[name]} />
      </g>
    </svg>
  );
}

const SESSION_TILE_VALUE: Record<TodayCompletionStatus, string> = {
  not_started: "Not started",
  started: "In progress",
  done: "Complete",
  modified: "Modified",
  skipped: "Skipped",
};

// One status tile. With a same-page target the whole tile is the jump-link to
// the section that resolves it; without one it is a plain readout.
function StatusTile({
  label,
  value,
  tone,
  icon,
  href,
  actionLabel,
}: {
  label: string;
  value: string;
  tone?: "pending" | "clear" | "risk";
  icon: TileIconName;
  href?: string;
  actionLabel: string;
}) {
  const body = (
    <>
      <span className={styles.tileIcon}>
        <TileIcon name={icon} ring />
      </span>
      <span className={styles.tileText}>
        <span className={styles.tileLabel}>{label}</span>
        <span className={styles.tileValue}>{value}</span>
      </span>
      {href ? <span className={styles.chevron} aria-hidden="true" /> : null}
    </>
  );
  return (
    <li className={styles.tile} data-tone={tone}>
      {href ? (
        <a href={href} className={styles.tileLink}>
          {body}
          <span className="sr-only">, {actionLabel}</span>
        </a>
      ) : (
        body
      )}
    </li>
  );
}

function TodayReadinessStrip({
  needsCheckin,
  openInjuryCount,
  completionStatus,
  checkinHref,
  injuriesHref,
  sessionHref,
}: {
  needsCheckin: boolean;
  openInjuryCount: number;
  completionStatus: TodayCompletionStatus;
  checkinHref?: string;
  injuriesHref?: string;
  sessionHref?: string;
}) {
  // Tones: pending (amber) = needs the athlete's action, clear (green) =
  // handled, risk (red) = open injuries. The session reads pending while in
  // progress and clear once any completion is logged.
  const sessionLogged =
    completionStatus === "done" ||
    completionStatus === "modified" ||
    completionStatus === "skipped";
  const sessionTone = sessionLogged ? "clear" : completionStatus === "started" ? "pending" : undefined;

  return (
    <ul className={styles.tiles} aria-label="Today command status">
      <StatusTile
        label="Check-in"
        value={needsCheckin ? "Due" : "Done"}
        tone={needsCheckin ? "pending" : "clear"}
        icon={needsCheckin ? "clock" : "check"}
        href={checkinHref}
        actionLabel="Go to today's check-in"
      />
      <StatusTile
        label="Today’s session"
        value={SESSION_TILE_VALUE[completionStatus] ?? getCompletionLabel(completionStatus)}
        tone={sessionTone}
        icon={sessionLogged ? "check" : completionStatus === "started" ? "pulse" : "clock"}
        href={sessionHref}
        actionLabel="Go to today's session"
      />
      <StatusTile
        label="Injuries"
        value={openInjuryCount ? `${openInjuryCount} active` : "None"}
        tone={openInjuryCount ? "risk" : "clear"}
        icon={openInjuryCount ? "injury" : "check"}
        href={injuriesHref}
        actionLabel="Go to injury manager"
      />
    </ul>
  );
}

export function TodayScreen() {
  const { session, me } = useAppSession();
  const token = session?.access_token ?? null;
  const {
    state,
    structuredPlan,
    planSchedule,
    rehabLabelPolicy,
    exerciseMedia,
    isLoading,
    error,
    refresh,
  } = useTodayCommand(token);

  const activePlan = state?.active_plan ?? {};
  const openOngoing = isOpenOngoingPlan(activePlan.fight_date);
  const planTitle = activePlan.name?.trim() || (openOngoing ? "Open training plan" : "Active fight camp");
  const hasPlan = hasActivePlan(activePlan);
  const showCheckin = state ? shouldShowTodayCheckin(state) : false;
  const trainingDayLabel = useMemo(
    () => formatTrainingDay(state?.today.training_day),
    [state?.today.training_day],
  );

  if (isLoading) {
    return <TodayLoadingState />;
  }
  if (error && (!state || /unauthorized|forbidden|not authenticated/i.test(error))) {
    const isAccessIssue = /unauthorized|forbidden|not authenticated/i.test(error);
    return (
      <section className="panel today-shell today-error-state">
        <div className="today-hero-copy">
          <p className="kicker">Today command feed</p>
          <h1>{isAccessIssue ? "Access is locked" : "Today is temporarily unavailable"}</h1>
          <p className="muted" role="alert">
            {isAccessIssue
              ? "Sign in with an active athlete account to unlock Today."
              : "The live check-in feed did not respond. Your saved plan has not changed."}
          </p>
          {process.env.NODE_ENV !== "production" ? (
            <p className="today-error-detail">Technical detail: {error}</p>
          ) : null}
        </div>
        <div className="today-action-row">
          <button type="button" className="cta" onClick={() => void refresh()}>
            Retry Today
          </button>
          <Link href="/plans" className="secondary-button">
            Open Plans
          </Link>
          <Link href="/timer" className="secondary-button">
            Round timer
          </Link>
          <Link href="/" className="ghost-button">
            Overview
          </Link>
        </div>
      </section>
    );
  }

  if (!state || !hasPlan) {
    return <NoActivePlanState />;
  }
  const resolvedDecision = resolveTodayDecision(state);
  const nextStep = getTodayNextStep(state, resolvedDecision);
  const supplementaryRisks = getSupplementaryRiskWatch(
    state.risk_watch,
    resolvedDecision,
  );
  const visibleTriggerLabels =
    resolvedDecision.displayTier === "preview" && !resolvedDecision.currentGuidanceBanner
      ? []
      : state.today.recommendation_trigger_labels;
  const commandRisks = getDistinctTodayRiskWatch(
    supplementaryRisks,
    visibleTriggerLabels,
  );
  const readinessForm = showCheckin ? (
    <TodayReadinessForm
      plan={activePlan}
      token={token ?? ""}
      warnings={state.today.warnings}
      onRefresh={refresh}
    />
  ) : null;
  const sessionPanel = (
    <TodaySessionPanel
      state={state}
      structuredPlan={structuredPlan}
      rehabLabelPolicy={rehabLabelPolicy}
      exerciseMedia={exerciseMedia}
      planSchedule={planSchedule}
      painReasonAllowed={hasHealthDataConsent(me)}
      token={token ?? ""}
      onRefresh={refresh}
      athleteFullName={me?.profile.full_name}
      commandUnavailable={Boolean(error)}
      professionalStatus={me?.profile.professional_status}
    />
  );

  return (
    <div className="today-page">
      {error ? (
        <section className="panel" role="alert">
          <p>Today could not refresh. Your entries are still here. Refresh before starting or saving a session.</p>
          <button type="button" className="secondary-button" onClick={() => void refresh()}>Retry Today</button>
        </section>
      ) : null}
      <section className={`panel today-shell ${styles.command}`}>
        <div className={styles.hero}>
          <div className="today-hero-copy">
            <p className={styles.heroDate}>{trainingDayLabel}</p>
            <h1>Today</h1>
            <p className={styles.heroPhase}>{openOngoing
              ? "Ongoing 4-week block"
              : activePlan.phase
                ? humanizeIfRawEnum(activePlan.phase)
                : null}</p>
          </div>
        </div>
        <TodayReadinessStrip
          needsCheckin={showCheckin}
          openInjuryCount={state.open_injuries?.length ?? 0}
          completionStatus={state.today.completion_status}
          checkinHref={showCheckin ? "#today-checkin" : undefined}
          injuriesHref={token ? "#today-injury" : undefined}
          sessionHref={resolvedDecision.displayTier === "preview" ? undefined : "#today-session"}
        />
        <TodayDecisionPanel
          banner={resolvedDecision.currentGuidanceBanner ?? resolvedDecision.banner}
          compactPreview={resolvedDecision.hasSession && !resolvedDecision.currentGuidanceBanner}
          tier={resolvedDecision.currentGuidanceBanner ? resolvedDecision.authoritativeTier : resolvedDecision.displayTier}
          triggers={state.today.recommendation_trigger_labels}
          safetyChecks={state.today.recommendation_safety_checks}
          context={state.today.recommendation_context_labels}
          sources={resolvedDecision.currentGuidanceBanner
            ? state.today.recommendation_sources?.filter((source) => source !== "today's planned session")
            : state.today.recommendation_sources}
          confidenceNote={state.today.recommendation_confidence_note}
        />
        <TodayRiskWatch
          risks={commandRisks}
          hasActiveInjury={(state.open_injuries?.length ?? 0) > 0}
        />
        {nextStep ? (
          <div className={styles.nextStep} role="status">
            <div>
              <p className={styles.nextStepTitle}>{nextStep.title}</p>
              <p className={styles.nextStepDetail}>{nextStep.detail}</p>
            </div>
            <Link href={nextStep.href}>{nextStep.action} <span aria-hidden="true">→</span></Link>
          </div>
        ) : null}
      </section>

      {resolvedDecision.useSafeReplacement ? (
        <>
          {sessionPanel}
          {readinessForm}
        </>
      ) : (
        <>
          {readinessForm}
          {sessionPanel}
        </>
      )}

      {token ? (
        <TodayInjuryManager
          openInjuries={state.open_injuries ?? []}
          effectiveClearance={state.effective_clinician_clearance}
          delayedPrompts={state.delayed_rehab_prompts}
          token={token}
          onRefresh={refresh}
        />
      ) : null}

      <nav className={styles.quickActions} aria-label="Quick actions">
        <p className={styles.quickTitle}>Quick actions</p>
        <div className={styles.quickRow}>
          {showCheckin ? (
            <a href="#today-checkin" className={styles.quickAction}>
              <TileIcon name="clock" />
              Check in
              <span className={styles.chevron} aria-hidden="true" />
            </a>
          ) : (
            <Link href="/timer" className={styles.quickAction}>
              <TileIcon name="timer" />
              Round timer
              <span className={styles.chevron} aria-hidden="true" />
            </Link>
          )}
          <Link href={`/plans/${activePlan.id}`} className={styles.quickAction}>
            <TileIcon name="plan" />
            View plan
            <span className={styles.chevron} aria-hidden="true" />
          </Link>
          <Link href="/history" className={styles.quickAction}>
            <TileIcon name="history" />
            History
            <span className={styles.chevron} aria-hidden="true" />
          </Link>
        </div>
      </nav>

      {resolvedDecision.recommendationState !== "not_checked_in" ? (
        <ContextualFeedback
          key={`daily-feedback-${state.active_plan?.id ?? "none"}-${state.today.training_day}`}
          token={token ?? ""}
          surface="daily_recommendation"
          className="today-feedback-card"
        />
      ) : null}
    </div>
  );
}
