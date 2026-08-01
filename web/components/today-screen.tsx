"use client";

import Link from "next/link";
import { useMemo } from "react";

import { useAppSession } from "@/components/auth-provider";
import { CampProgressBar } from "@/components/camp-progress-bar";
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
import { useTrainingDay } from "@/lib/use-training-day";
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
      </div>
    </section>
  );
}

// A status value that, when a same-page target exists, doubles as a jump-link to
// the section that resolves it — so the strip reads as a decision surface, not
// just a status readout. Cells without a live target render as plain text.
function ReadinessValue({
  children,
  href,
  actionLabel,
}: {
  children: React.ReactNode;
  href?: string;
  actionLabel?: string;
}) {
  if (!href) {
    return <dd>{children}</dd>;
  }
  return (
    <dd>
      <a href={href}>
        {children}
        {actionLabel ? <span className="sr-only"> — {actionLabel}</span> : null}
      </a>
    </dd>
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
  const injuryLabel = openInjuryCount
    ? `${openInjuryCount} active injur${openInjuryCount === 1 ? "y" : "ies"}`
    : "No active injuries";
  // Status-dot tones: pending (amber, pulsing) = needs the athlete's action,
  // clear (green) = handled, risk (red, pulsing) = open injuries. The session
  // cell reads pending while in progress and clear once any completion is
  // logged (done / modified / skipped all count as "logged for today").
  const sessionLogged =
    completionStatus === "done" ||
    completionStatus === "modified" ||
    completionStatus === "skipped";
  const sessionTone = sessionLogged ? "clear" : completionStatus === "started" ? "pending" : undefined;

  return (
    <dl className="today-readiness-strip" aria-label="Today command status">
      <div data-tone={needsCheckin ? "pending" : "clear"}>
        <dt>Check-in</dt>
        <ReadinessValue href={checkinHref} actionLabel="Go to today's check-in">
          {needsCheckin ? "Due" : "Logged"}
        </ReadinessValue>
      </div>
      <div data-tone={openInjuryCount ? "risk" : "clear"}>
        <dt>Injury</dt>
        <ReadinessValue href={injuriesHref} actionLabel="Go to injury manager">
          {injuryLabel}
        </ReadinessValue>
      </div>
      <div data-tone={sessionTone}>
        <dt>Session</dt>
        <ReadinessValue href={sessionHref} actionLabel="Go to today's session">
          {getCompletionLabel(completionStatus)}
        </ReadinessValue>
      </div>
    </dl>
  );
}

export function TodayScreen() {
  const { session } = useAppSession();
  const token = session?.access_token ?? null;
  const trainingDay = useTrainingDay();
  const { state, structuredPlan, planSchedule, rehabLabelPolicy, isLoading, error, refresh } =
    useTodayCommand(token);

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
  if (error) {
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
  const supplementaryRisks = getSupplementaryRiskWatch(
    state.risk_watch,
    resolvedDecision,
  );
  const visibleTriggerLabels =
    resolvedDecision.displayTier === "preview"
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
      planSchedule={planSchedule}
      token={token ?? ""}
      onRefresh={refresh}
    />
  );

  return (
    <div className="today-page">
      <section className="panel today-shell">
        <div className="today-hero-grid">
          <div className="today-hero-copy">
            <p className="kicker">Today</p>
            <h1>{planTitle}</h1>
            <p className="muted today-hero-meta">
              {trainingDayLabel}
              {openOngoing || activePlan.phase ? <span aria-hidden="true"> · </span> : null}
              {openOngoing
                ? "Ongoing 4-week block"
                : activePlan.phase
                  ? humanizeIfRawEnum(activePlan.phase)
                  : null}
            </p>
          </div>
          <div className="today-hero-actions">
            <Link href={`/plans/${activePlan.id}`} className="secondary-button">
              Open camp plan
            </Link>
            <Link href="/history" className="ghost-button">
              View history
            </Link>
            <Link href="/" className="ghost-button">
              Overview
            </Link>
          </div>
        </div>
        <CampProgressBar plan={structuredPlan} trainingDay={trainingDay} variant="today" />
        <TodayReadinessStrip
          needsCheckin={showCheckin}
          openInjuryCount={state.open_injuries?.length ?? 0}
          completionStatus={state.today.completion_status}
          checkinHref={showCheckin ? "#today-checkin" : undefined}
          injuriesHref={token ? "#today-injury" : undefined}
          sessionHref="#today-session"
        />
        <TodayDecisionPanel
          banner={resolvedDecision.banner}
          tier={resolvedDecision.displayTier}
          triggers={state.today.recommendation_trigger_labels}
          safetyChecks={state.today.recommendation_safety_checks}
          context={state.today.recommendation_context_labels}
          sources={state.today.recommendation_sources}
          confidenceNote={state.today.recommendation_confidence_note}
        />
        <TodayRiskWatch
          risks={commandRisks}
          hasActiveInjury={(state.open_injuries?.length ?? 0) > 0}
        />
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
          token={token}
          onRefresh={refresh}
        />
      ) : null}

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
