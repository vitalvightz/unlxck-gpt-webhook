"use client";

import Link from "next/link";
import { TrainingHabitLog } from "@/components/training-habit-log";
import { useMemo, useState } from "react";
import styles from "./today-screen.module.css";

import { useAppSession } from "@/components/auth-provider";
import { useConnectivity, useOnReconnect } from "@/components/connection-status-banner";
import { hasHealthDataConsent } from "@/lib/compliance";
import { ContextualFeedback } from "@/components/feedback/contextual-feedback";
import { Skeleton } from "@/components/skeleton";
import { formatTrainingDay } from "@/components/today/format";
import { TodayDecisionPanel } from "@/components/today/today-decision-panel";
import { TodayInjuryManager } from "@/components/today/today-injury-manager";
import { TodayReadinessForm } from "@/components/today/today-readiness-form";
import { TodayRiskWatch } from "@/components/today/today-risk-watch";
import { StandaloneRehab } from "@/components/today/standalone-rehab";
import { TodaySessionPanel } from "@/components/today/today-session-panel";
import { useTodayCommand } from "@/components/today/use-today-command";
import { humanizeIfRawEnum } from "@/lib/plan-labels";
import { isOpenOngoingPlan } from "@/lib/plan-format";
import { getTodayNextStep } from "@/lib/today-next-step";
import { rehabExerciseTarget } from "@/lib/rehab-exercise-guide";
import {
  getCompletionLabel,
  getDistinctTodayRiskWatch,
  getPlanFreeGuidanceBanner,
  getSupplementaryRiskWatch,
  hasActivePlan,
  resolveTodayDecision,
  shouldShowTodayCheckin,
} from "@/lib/today-authoritative";
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
  hasPlan,
  canCheckIn,
  loggedToday,
  needsCheckin,
  openInjuryCount,
  completionStatus,
  checkinHref,
  injuriesHref,
  sessionHref,
}: {
  hasPlan: boolean;
  canCheckIn: boolean;
  loggedToday: boolean | null;
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
      {/* The check-in is the same with or without a plan. Without health-data
          consent there is none, so it must not read as due or as done. */}
      {canCheckIn ? (
        <StatusTile
          label="Check-in"
          value={needsCheckin ? "Due" : "Done"}
          tone={needsCheckin ? "pending" : "clear"}
          icon={needsCheckin ? "clock" : "check"}
          href={checkinHref}
          actionLabel="Go to today's check-in"
        />
      ) : (
        <StatusTile label="Readiness" value="Not assessed" icon="pulse" actionLabel="" />
      )}
      {hasPlan ? (
        <StatusTile
          label="Today’s session"
          value={SESSION_TILE_VALUE[completionStatus] ?? getCompletionLabel(completionStatus)}
          tone={sessionTone}
          icon={sessionLogged ? "check" : completionStatus === "started" ? "pulse" : "clock"}
          href={sessionHref}
          actionLabel="Go to today's session"
        />
      ) : (
        <StatusTile
          label="Training"
          value={loggedToday ? "Logged" : "Log session"}
          tone={loggedToday ? "clear" : undefined}
          icon={loggedToday ? "check" : "history"}
          href="#today-training-log"
          actionLabel="Go to the training log"
        />
      )}
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
    isRefreshing,
    error,
    refresh,
    patchSession,
  } = useTodayCommand(token);
  const { offline: isOffline } = useConnectivity();
  useOnReconnect(() => void refresh(), Boolean(error));

  const activePlan = state?.active_plan ?? {};
  const openOngoing = isOpenOngoingPlan(activePlan.fight_date);
  const planTitle = activePlan.name?.trim() || (openOngoing ? "Open training plan" : "Active fight camp");
  const hasPlan = hasActivePlan(activePlan);
  // Readiness answers are health data. Without a plan the check-in is only
  // offered with consent; the planned check-in keeps its existing behaviour
  // (the server enforces consent for both).
  const canCheckIn = hasPlan || hasHealthDataConsent(me);
  const showCheckin = state && canCheckIn ? shouldShowTodayCheckin(state) : false;
  // Unknown (null) until shared history confirms it; never assumed.
  const [loggedToday, setLoggedToday] = useState<boolean | null>(null);
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
          <h1>
            {isAccessIssue
              ? "Access is locked"
              : isOffline
                ? "You’re offline."
                : "Today is temporarily unavailable"}
          </h1>
          <p className="muted" role="alert">
            {isAccessIssue
              ? "Sign in with an active athlete account to unlock Today."
              : isOffline
                ? "Your saved training hasn’t changed. Today reloads the moment you reconnect."
                : "The live Today feed did not respond. Your saved training has not changed."}
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

  // A missing feed is never read as "no plan" or "no injuries".
  if (!state) {
    return <TodayLoadingState />;
  }
  const resolvedDecision = resolveTodayDecision(state);
  const nextStep = getTodayNextStep(state, resolvedDecision);
  const availableRehabInjuries = new Set((state.open_injuries ?? []).filter(injury => {
    const decision = injury.rehab_decision;
    return decision?.outcome === "prescribed_rehab" && (decision.schedule?.state === "due"
      || (state.live_prescription?.session.completion_status ?? state.today.completion_status) === "started" && decision.schedule?.state === "already_completed"
        && /started session/i.test(decision.schedule.reason));
  }).map(injury => injury.id));
  const rehabBlocks = (hasPlan ? resolvedDecision.sessionIsToday : Boolean(state.live_prescription?.rehab_only)) && !error && !isRefreshing
    && !state.live_prescription?.safety_hold
    && !["done", "modified", "skipped"].includes(state.live_prescription?.session.completion_status ?? state.today.completion_status)
    ? (state.live_prescription?.session.blocks ?? []).filter(block => rehabExerciseTarget(block)
      && availableRehabInjuries.has(block.injury_id ?? "")) : [];
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
  // With no programme there is no session to preview: the lead is today's
  // readiness, an injury hold or a safety notice, worded without a session.
  const decisionBanner = hasPlan
    ? resolvedDecision.currentGuidanceBanner ?? resolvedDecision.banner
    : getPlanFreeGuidanceBanner(state, resolvedDecision);
  const readinessForm = showCheckin ? (
    <TodayReadinessForm
      plan={hasPlan ? activePlan : undefined}
      token={token ?? ""}
      warnings={state.today.warnings}
      onRefresh={refresh}
    />
  ) : null;
  const sessionPanel = hasPlan ? (
    <TodaySessionPanel
      state={state}
      structuredPlan={structuredPlan}
      rehabLabelPolicy={rehabLabelPolicy}
      exerciseMedia={{ ...exerciseMedia, ...state.exercise_media }}
      planSchedule={planSchedule}
      painReasonAllowed={hasHealthDataConsent(me)}
      token={token ?? ""}
      onRefresh={refresh}
      athleteFullName={me?.profile.full_name}
      commandUnavailable={Boolean(error)}
      onPlanSessionChanged={patchSession}
      professionalStatus={me?.profile.professional_status}
    />
  ) : <StandaloneRehab key={state.live_prescription?.session.session_id ?? "rehab"} state={state} token={token ?? ""} unavailable={Boolean(error) || isRefreshing} onRefresh={refresh} />;

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
            {hasPlan ? (
              <p className={styles.heroPhase}>{openOngoing
                ? "Ongoing 4-week block"
                : activePlan.phase
                  ? humanizeIfRawEnum(activePlan.phase)
                  : null}</p>
            ) : (
              <p className={styles.heroIntro}>Your training, your record. Log sessions from your coach or your own training.</p>
            )}
          </div>
          {/* Without a programme the logger itself leads directly below. */}
          {hasPlan ? <a className={styles.logTrainingLink} href="#today-training-log">Log session</a> : null}
        </div>
        <TodayReadinessStrip
          hasPlan={hasPlan}
          canCheckIn={canCheckIn}
          loggedToday={loggedToday}
          needsCheckin={showCheckin}
          openInjuryCount={state.open_injuries?.length ?? 0}
          completionStatus={state.today.completion_status}
          checkinHref={showCheckin ? "#today-checkin" : undefined}
          injuriesHref={token ? "#today-injury" : undefined}
          sessionHref={resolvedDecision.displayTier === "preview" ? undefined : "#today-session"}
        />
        {rehabBlocks.length ? <nav className={styles.rehabAccess} aria-label="Your rehab">
          <p className={styles.nextStepTitle}>Your rehab</p>
          {rehabBlocks.map(block => <a key={block.block_id}
            href={`#${encodeURIComponent(rehabExerciseTarget(block)!)}`}>
            <span>{block.display_name}</span><strong>View rehab <span aria-hidden="true">→</span></strong>
          </a>)}
        </nav> : null}
        {isRefreshing ? <p role="status">Updating Today…</p> : error ? null : <TodayDecisionPanel
          banner={decisionBanner}
          compactPreview={resolvedDecision.hasSession && !resolvedDecision.currentGuidanceBanner}
          tier={resolvedDecision.currentGuidanceBanner ? resolvedDecision.authoritativeTier : resolvedDecision.displayTier}
          triggers={state.today.recommendation_trigger_labels}
          safetyChecks={state.today.recommendation_safety_checks}
          context={state.today.recommendation_context_labels}
          sources={resolvedDecision.currentGuidanceBanner
            ? state.today.recommendation_sources?.filter((source) => source !== "today's planned session")
            : state.today.recommendation_sources}
          confidenceNote={state.today.recommendation_confidence_note}
        />}
        <TodayRiskWatch
          risks={commandRisks}
          hasActiveInjury={(state.open_injuries?.length ?? 0) > 0}
        />
        {nextStep && !isRefreshing && !error ? (
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

      <div id="today-training-log" className={styles.trainingLog} tabIndex={-1}>
        <TrainingHabitLog
          accessToken={token}
          state={state}
          variant={hasPlan ? "compact" : "primary"}
          onLoggedToday={setLoggedToday}
          onSaved={() => void refresh()}
        />
      </div>

      {/* Injury reports are health data: the server rejects them without
          consent, so a new report is never offered until it is granted. Open
          injuries stay visible regardless, with their restrictions. */}
      {token && (hasHealthDataConsent(me) || (state.open_injuries?.length ?? 0) > 0) ? (
        <TodayInjuryManager
          openInjuries={state.open_injuries ?? []}
          rehabTargets={Object.fromEntries(rehabBlocks.map(block => [block.injury_id!, `#${encodeURIComponent(rehabExerciseTarget(block)!)}`]))}
          effectiveClearance={state.effective_clinician_clearance}
          delayedPrompts={state.delayed_rehab_prompts}
          todaySafetyNoticeInjuryId={state.today.primary_safety_notice?.injury_id ?? null}
          token={token}
          onRefresh={refresh}
        />
      ) : token ? (
        <section id="today-injury" className={`panel ${styles.injuryConsent}`} aria-labelledby="today-injury-consent-heading">
          <h2 id="today-injury-consent-heading">Injuries</h2>
          <p className="muted">Reporting an injury uses health information, so it needs your health-data consent.</p>
          <Link href="/settings#privacy" className="secondary-button">Review consent</Link>
        </section>
      ) : null}

      <nav className={styles.quickActions} aria-label="Quick actions">
        <p className={styles.quickTitle}>Quick actions</p>
        <div className={hasPlan ? styles.quickRow : `${styles.quickRow} ${styles.quickRowFour}`}>
          {/* Without a plan the round timer stays: the check-in has its own tile. */}
          {showCheckin && hasPlan ? (
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
          {hasPlan ? (
            <Link href={`/plans/${activePlan.id}`} className={styles.quickAction}>
              <TileIcon name="plan" />
              View plan
              <span className={styles.chevron} aria-hidden="true" />
            </Link>
          ) : (me?.plan_count ?? 0) > 0 ? (
            <Link href="/plans" className={styles.quickAction}>
              <TileIcon name="plan" />
              Choose a plan
              <span className={styles.chevron} aria-hidden="true" />
            </Link>
          ) : (
            <Link href="/quick-build" className={styles.quickAction}>
              <TileIcon name="plan" />
              Generate my S&amp;C plan
              <span className={styles.chevron} aria-hidden="true" />
            </Link>
          )}
          {hasPlan ? null : (
            // Coach-led athletes put their coach's sessions into a plan of their own.
            <Link href="/plans/custom" className={styles.quickAction}>
              <TileIcon name="plan" />
              Build your own plan
              <span className={styles.chevron} aria-hidden="true" />
            </Link>
          )}
          <Link href="/history" className={styles.quickAction}>
            <TileIcon name="history" />
            History
            <span className={styles.chevron} aria-hidden="true" />
          </Link>
        </div>
      </nav>

      {hasPlan && resolvedDecision.recommendationState !== "not_checked_in" ? (
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
