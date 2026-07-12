"use client";

import Link from "next/link";
import { useMemo } from "react";

import { useAppSession } from "@/components/auth-provider";
import { CampProgressBar } from "@/components/camp-progress-bar";
import { Skeleton } from "@/components/skeleton";
import { formatTrainingDay } from "@/components/today/format";
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
  hasActivePlan,
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
        <Link href="/intake" className="cta">
          Complete Intake
        </Link>
      </div>
    </section>
  );
}

function TodayReadinessStrip({
  needsCheckin,
  openInjuryCount,
  completionStatus,
}: {
  needsCheckin: boolean;
  openInjuryCount: number;
  completionStatus: TodayCompletionStatus;
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
        <dd>{needsCheckin ? "Due" : "Logged"}</dd>
      </div>
      <div data-tone={openInjuryCount ? "risk" : "clear"}>
        <dt>Injury</dt>
        <dd>{injuryLabel}</dd>
      </div>
      <div data-tone={sessionTone}>
        <dt>Session</dt>
        <dd>{getCompletionLabel(completionStatus)}</dd>
      </div>
    </dl>
  );
}

export function TodayScreen() {
  const { session } = useAppSession();
  const token = session?.access_token ?? null;
  const trainingDay = useTrainingDay();
  const { state, structuredPlan, isLoading, error, refresh } = useTodayCommand(token);

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
              View full plan
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
        />
        <TodayRiskWatch risks={state.risk_watch} />
      </section>

      {showCheckin ? (
        <TodayReadinessForm
          plan={activePlan}
          token={token ?? ""}
          warnings={state.today.warnings}
          onRefresh={refresh}
        />
      ) : null}

      {token ? (
        <TodayInjuryManager
          openInjuries={state.open_injuries ?? []}
          token={token}
          onRefresh={refresh}
        />
      ) : null}

      <TodaySessionPanel
        state={state}
        structuredPlan={structuredPlan}
        token={token ?? ""}
        onRefresh={refresh}
      />
    </div>
  );
}
