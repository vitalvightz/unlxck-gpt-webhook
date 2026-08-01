"use client";

import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { type ReactNode, useCallback, useEffect, useId, useRef, useState } from "react";

import { useAppSession } from "@/components/auth-provider";
import { CampProgressBar } from "@/components/camp-progress-bar";
import { EmptyState } from "@/components/empty-state";
import { InstallUnlxck } from "@/components/install-unlxck";
import { PlansFeaturedSkeleton, Skeleton } from "@/components/skeleton";
import { getPlan, getToday } from "@/lib/api";
import { useTrainingDay } from "@/lib/use-training-day";
import {
  getOptionLabel,
  PROFESSIONAL_STATUS_OPTIONS,
  STANCE_OPTIONS,
  TACTICAL_STYLE_OPTIONS,
  TECHNICAL_STYLE_OPTIONS,
} from "@/lib/intake-options";
import { humanizeIfRawEnum } from "@/lib/plan-labels";
import { formatPlanFightDate, formatPlanTimestamp, getPlanDisplayName, isOpenOngoingPlan } from "@/lib/plan-format";
import {
  getCampDayLabel,
  getCompletionLabel,
  getOverviewPrimaryAction,
  getRiskWatchSummary,
  getRiskWatchText,
  getSafeSessionView,
  getSessionDayLabel,
  getSessionFocus,
  getSessionTitle,
  getTierMeta,
  isHardCombatSession,
  resolveTodayDecision,
  type TodayDecisionTier,
} from "@/lib/today";
import {
  LANDING_OUTCOME_POINTS,
  LANDING_PRODUCT_PROOF_POINTS,
  LANDING_WORKFLOW_STEPS,
  LANDING_WORKSPACE_ROWS,
  PUBLIC_HERO_SUMMARY,
} from "@/lib/public-landing-copy";
import type { PlanSummary, StructuredPlan, TodayActivePlan, TodayCommandView, TodaySession } from "@/lib/types";

function formatPlanCount(value: number): string {
  return `${value} saved plan${value === 1 ? "" : "s"}`;
}

function OverviewDetailList({
  items,
}: {
  items: Array<{
    label: string;
    value: string;
    highlight?: boolean;
    badgeText?: string;
    helperText?: string;
    progressValue?: number;
  }>;
}) {
  return (
    <div className="review-detail-list overview-detail-list">
      {items.map((item) => (
        <div
          key={`${item.label}-${item.value}`}
          className={item.highlight ? "review-detail-row overview-detail-row-highlight" : "review-detail-row"}
        >
          <div className={item.highlight ? "overview-detail-heading overview-detail-heading-highlight" : "overview-detail-heading"}>
            <p className="review-detail-label">{item.label}</p>
            {item.badgeText ? <span className="overview-inline-badge">{item.badgeText}</span> : null}
          </div>
          <p className={item.highlight ? "review-detail-value overview-detail-value-strong" : "review-detail-value"}>{item.value}</p>
          {typeof item.progressValue === "number" ? (
            <div className="overview-progress-track" role="presentation" aria-hidden="true">
              <span
                className="overview-progress-fill"
                style={{ width: `${Math.max(0, Math.min(100, item.progressValue))}%` }}
              />
            </div>
          ) : null}
          {item.helperText ? <p className="overview-progress-helper">{item.helperText}</p> : null}
        </div>
      ))}
    </div>
  );
}

function OverviewDetailGrid({
  items,
}: {
  items: Array<{
    label: string;
    value: string;
    highlight?: boolean;
    badgeText?: string;
    helperText?: string;
    progressValue?: number;
  }>;
}) {
  const midpoint = Math.ceil(items.length / 2);
  const columns = [items.slice(0, midpoint), items.slice(midpoint)].filter((column) => column.length);

  return (
    <div className="overview-detail-grid">
      {columns.map((column, index) => (
        <div key={`column-${index + 1}`} className="overview-detail-column">
          <OverviewDetailList items={column} />
        </div>
      ))}
    </div>
  );
}

function OverviewDisclosure({
  title,
  summary,
  badge,
  children,
}: {
  title: string;
  summary: string;
  badge?: string;
  children: ReactNode;
}) {
  return (
    <details className="overview-disclosure">
      <summary className="overview-disclosure-summary">
        <div className="overview-disclosure-copy">
          <p className="kicker">{title}</p>
          <p className="overview-disclosure-title">{summary}</p>
        </div>
        <div className="overview-disclosure-meta">
          {badge ? <span className="overview-inline-badge">{badge}</span> : null}
          <span className="overview-disclosure-chevron" aria-hidden="true" />
        </div>
      </summary>
      <div className="overview-disclosure-body">{children}</div>
    </details>
  );
}

function WorkspaceOverviewSkeleton() {
  return (
    <>
      <section
        className="hero-panel overview-command-shell overview-command-primary athlete-motion-slot athlete-motion-header"
        aria-busy="true"
      >
        <div className="overview-primary-grid">
          <div className="status-card overview-command-card overview-decision-lead">
            <Skeleton variant="text" width={110} height={12} />
            <Skeleton variant="text" width="70%" height={40} />
            <Skeleton variant="text" width="88%" height={16} />
            <Skeleton variant="text" width="76%" height={16} />
            <div className="plan-summary-actions overview-primary-actions">
              <Skeleton variant="block" width={168} height={44} />
              <Skeleton variant="block" width={140} height={44} />
            </div>
          </div>
          <div className="overview-primary-session">
            <PlansFeaturedSkeleton />
          </div>
        </div>
      </section>
      <section className="panel overview-secondary athlete-motion-slot athlete-motion-status" aria-busy="true">
        <div className="overview-operational-strip" aria-label="Workspace status loading">
          {[0, 1, 2, 3].map((index) => (
            <div key={index} className="overview-operational-item">
              <Skeleton variant="text" width={72} height={10} />
              <Skeleton variant="text" width={120} height={16} />
            </div>
          ))}
        </div>
        <PlansFeaturedSkeleton />
      </section>
    </>
  );
}

function enrichConfirmedActivePlan(
  commandPlan: TodayActivePlan | null | undefined,
  latestPlan: PlanSummary | null | undefined,
): TodayActivePlan {
  if (!commandPlan?.id) {
    return commandPlan ?? {};
  }

  const canUseLatestPlanFields = latestPlan?.plan_id === commandPlan.id;
  if (!canUseLatestPlanFields) {
    return commandPlan;
  }

  return {
    ...commandPlan,
    name: commandPlan.name || getPlanDisplayName(latestPlan),
    status: commandPlan.status || latestPlan.status,
    fight_date: commandPlan.fight_date || latestPlan.fight_date,
  };
}

/**
 * Overview risk watch. Shows the two highest-priority flags, with any extras
 * behind an in-place "+N more" toggle so the card expands smoothly instead of
 * routing away or truncating. Row copy runs through getRiskWatchText so a flag
 * never parrots the main recommendation word-for-word.
 */
function OverviewRiskWatch({
  risks = [],
  tier,
}: {
  risks?: TodayCommandView["risk_watch"];
  tier?: TodayDecisionTier;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const overflowId = useId();

  if (!risks.length) {
    return (
      <article className="status-card overview-command-card overview-risk-card">
        <p className="status-label">Risk watch</p>
        <p className="muted">No active warnings.</p>
      </article>
    );
  }

  const safeRisks = risks ?? [];
  const visible = safeRisks.slice(0, 2);
  const overflow = safeRisks.length - visible.length;
  const shown = isExpanded ? safeRisks : visible;
  const summary = getRiskWatchSummary(safeRisks, tier);

  return (
    <article className="status-card overview-command-card overview-risk-card">
      <p className="status-label">Risk watch</p>
      <div id={overflowId} className="overview-risk-list">
        {shown.map((risk, index) => (
          <div key={`${risk.category}-${risk.label}-${index}`} className="overview-risk-row" data-tone={risk.tone}>
            <span className="overview-risk-row-label">{humanizeIfRawEnum(risk.label) || risk.label}</span>
            <span className="overview-risk-row-text">{getRiskWatchText(risk)}</span>
          </div>
        ))}
      </div>
      {overflow > 0 ? (
        <button
          type="button"
          className="overview-risk-more"
          aria-controls={overflowId}
          aria-expanded={isExpanded}
          onClick={() => setIsExpanded((current) => !current)}
        >
          {isExpanded ? "Show less" : `+${overflow} more warning${overflow > 1 ? "s" : ""}`}
        </button>
      ) : null}
      <p className="overview-risk-footer">
        <span>{summary.count} active warning{summary.count === 1 ? "" : "s"}</span>
        <span className="overview-risk-strongest">Strongest signal: {summary.strongestLabel}</span>
      </p>
    </article>
  );
}

export default function HomePage() {
  const { isReady, isMeHydrated, hasTransientMeError, session, me, signOut, refreshMe } = useAppSession();
  const router = useRouter();
  const trainingDay = useTrainingDay();
  const [commandState, setCommandState] = useState<TodayCommandView | null>(null);
  const [commandError, setCommandError] = useState<string | null>(null);
  const [structuredPlan, setStructuredPlan] = useState<StructuredPlan | null>(null);

  useEffect(() => {
    if (isReady && session && isMeHydrated && !me) {
      router.replace("/login");
    }
  }, [isReady, isMeHydrated, me, router, session]);

  const [isReloadingCommand, setIsReloadingCommand] = useState(false);
  const latestTokenRef = useRef(session?.access_token);

  useEffect(() => {
    latestTokenRef.current = session?.access_token;
  }, [session?.access_token]);

  const loadCommandState = useCallback(async () => {
    const token = session?.access_token;
    if (!token) {
      setCommandState(null);
      return;
    }
    setIsReloadingCommand(true);
    setCommandError(null);
    try {
      const state = await getToday(token);
      // Ignore results from a request the current session has moved past.
      if (latestTokenRef.current !== token) {
        return;
      }
      setCommandState(state);
      setCommandError(null);
    } catch {
      if (latestTokenRef.current !== token) {
        return;
      }
      setCommandError("We couldn't load your camp status. Please try again.");
    } finally {
      if (latestTokenRef.current === token) {
        setIsReloadingCommand(false);
      }
    }
  }, [session?.access_token]);

  useEffect(() => {
    let active = true;
    if (!session?.access_token) {
      setCommandState(null);
      return () => {
        active = false;
      };
    }
    void getToday(session.access_token)
      .then((state) => {
        if (!active) return;
        setCommandState(state);
        setCommandError(null);
      })
      .catch(() => {
        if (!active) return;
        setCommandError("We couldn't load your camp status. Please try again.");
      });
    return () => {
      active = false;
    };
  }, [session?.access_token]);

  // Best-effort structured plan for the camp-progress bar. Read-only: if it
  // fails, Overview just hides the bar (the rest of the command view is
  // unaffected). Mirrors how Today loads the same data.
  const activePlanId = commandState?.active_plan?.id;
  useEffect(() => {
    const token = session?.access_token;
    if (!token || !activePlanId) {
      setStructuredPlan(null);
      return;
    }
    let cancelled = false;
    getPlan(token, activePlanId)
      .then((detail) => {
        if (!cancelled) {
          setStructuredPlan(detail.outputs?.structured_plan ?? null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStructuredPlan(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [session?.access_token, activePlanId]);

  if (session && hasTransientMeError) {
    return (
      <section className="panel loading-card">
        <p className="kicker">Overview</p>
        <h1>Workspace temporarily unavailable</h1>
        <p className="muted">We couldn&apos;t load your athlete profile. Please try again.</p>
        <div className="hero-actions">
          <button type="button" className="cta" onClick={() => void refreshMe()}>
            Retry
          </button>
          <button type="button" className="secondary-button" onClick={() => void signOut()}>
            Sign out
          </button>
        </div>
      </section>
    );
  }

  if (!isReady) {
    return (
      <section className="panel loading-card">
        <p className="kicker">Overview</p>
        <h1>Loading your athlete workspace</h1>
        <p className="muted">Checking saved intake and plan history.</p>
      </section>
    );
  }

  if (session && !isMeHydrated) {
    return <WorkspaceOverviewSkeleton />;
  }

  if (session && isMeHydrated && !me) {
    return (
      <section className="panel loading-card">
        <p className="kicker">Overview</p>
        <h1>Redirecting to login</h1>
        <p className="muted">Session expired. Sign in again.</p>
      </section>
    );
  }

  if (session && me) {
    const latestPlan = me.latest_plan ?? null;
    const draft = (me.profile.onboarding_draft as { current_step?: number } | null) ?? null;
    const latestIntake = me.latest_intake;
    const hasMeaningfulDraft = Boolean(
      draft && typeof draft === "object" && Object.keys(draft as Record<string, unknown>).length > 0,
    );
    const isFirstTimeUser =
      me.plan_count === 0 && !latestPlan && !latestIntake && !hasMeaningfulDraft;

    if (isFirstTimeUser) {
      return (
        <section className="hero-panel welcome-panel athlete-motion-slot athlete-motion-header">
          <div className="hero-panel-copy welcome-copy">
            <p className="eyebrow">Welcome to UNLXCK</p>
            <h1 className="hero-title">Build your fight camp in minutes.</h1>
            <p className="overview-command-summary">
              Create your athlete profile, generate a structured camp plan, and manage your setup from one dashboard.
            </p>
            <p className="muted welcome-context">
              Designed for fighters and combat athletes. Quick Build takes about 2 minutes. Advanced Intake gives more control.
            </p>
            <div className="hero-actions welcome-actions">
              <Link href="/onboarding" className="cta">
                Start Advanced Intake
              </Link>
              <Link href="/quick-build" className="secondary-button">
                Use Quick Build
              </Link>
              <Link href="/demo-plan" className="ghost-button">
                View Demo Plan
              </Link>
            </div>
          </div>
        </section>
      );
    }

    if (!commandState && !commandError) {
      return <WorkspaceOverviewSkeleton />;
    }

    if (!commandState && commandError) {
      return (
        <section className="panel loading-card">
          <p className="kicker">Overview</p>
          <h1>Camp command view unavailable</h1>
          <p className="muted">{commandError}</p>
          <div className="hero-actions">
            <button type="button" className="cta" onClick={() => window.location.reload()}>
              Retry
            </button>
            <Link href="/plans" className="secondary-button">
              View plans
            </Link>
          </div>
        </section>
      );
    }

    const activePlan = enrichConfirmedActivePlan(commandState?.active_plan, latestPlan);
    const hasActivePlan = Boolean(activePlan.id);
    // "No active plan" splits into two states the whole primary area must agree
    // on: saved plans exist (pick one) vs no plans at all (build the first).
    const hasSavedPlans = (me.plan_count ?? 0) > 0;
    const sessionPreview = (commandState?.today?.next_session ?? {}) as TodaySession;
    const resolvedDecision = commandState ? resolveTodayDecision(commandState) : null;
    const hasNextSession = resolvedDecision?.hasSession ?? false;
    const nextSessionTitle = hasNextSession ? getSessionTitle(sessionPreview) : "No upcoming session";
    const nextSessionDay = hasNextSession ? getSessionDayLabel(sessionPreview) : "";
    const nextSessionFocus = hasNextSession
      ? getSessionFocus(sessionPreview)
      : hasActivePlan
        ? "Open Today for the matched session."
        : hasSavedPlans
          ? "Select a saved plan to see its next session."
          : "Build a plan to see your first session.";
    const risks = commandState?.risk_watch ?? [];
    const recommendation = commandState?.today?.recommendation_state ?? "not_checked_in";
    // Overview consumes the same authoritative resolver as Today. The backend
    // tier controls safety; structured severe-injury data only supplies truthful
    // STOP presentation and the injury check-in action.
    const decisionBanner = resolvedDecision?.banner ?? null;
    const decisionTier = resolvedDecision?.displayTier ?? "not_checked_in";
    const tierMeta = getTierMeta(decisionTier);
    const decisionTitle = tierMeta.label;
    const decisionLines = decisionBanner
      ? [decisionBanner.detail, decisionBanner.action].filter((line): line is string => Boolean(line))
      : ["Submit today's fast check-in to unlock your training decision."];
    const decisionSafety = decisionBanner?.safety;
    // With no active plan there is no training decision to render, so the whole
    // primary area (headline + body) is overridden to match the CTA instead of
    // showing a stale "CHECK IN REQUIRED" that the athlete cannot act on.
    const overviewTitle = !hasActivePlan
      ? hasSavedPlans
        ? "Select active plan"
        : "Build your plan"
      : decisionTitle;
    const overviewLines = !hasActivePlan
      ? [
          hasSavedPlans
            ? "Choose which saved plan should control Today, check-ins and session tracking."
            : "Create your first plan to unlock Today and session tracking.",
        ]
      : decisionLines;
    // Safety copy only belongs to a real decision — never on the no-plan states.
    const overviewSafety = hasActivePlan ? decisionSafety : undefined;
    // Today's countdown to the fight, and whether the scheduled session is today
    // (vs a future planned day that must read as pending, not cleared).
    const campDay = getCampDayLabel(commandState?.today?.training_day, String(activePlan.fight_date || ""));
    const openOngoing = hasActivePlan && isOpenOngoingPlan(activePlan.fight_date);
    const sessionIsToday = resolvedDecision?.sessionIsToday ?? false;
    const nextIsHardCombat = hasNextSession && isHardCombatSession(sessionPreview);
    // STOP + the scheduled session is today -> replace it with a safe session.
    // Any future scheduled session -> show it as pending clearance, never cleared.
    const safeSession = resolvedDecision?.useSafeReplacement
      ? getSafeSessionView(nextSessionTitle, commandState?.open_injuries)
      : null;
    const showNextPlanned = hasNextSession && !sessionIsToday;
    // When today's session has already been logged (modified / done / skipped),
    // surface that state on the session card so a modified day reads clearly and
    // is not mistaken for an untouched session.
    const todayCompletionStatus = commandState?.today?.completion_status;
    const sessionStateLabel =
      sessionIsToday && todayCompletionStatus && todayCompletionStatus !== "not_started"
        ? getCompletionLabel(todayCompletionStatus)
        : null;
    // Decision tone drives the colour accents on the decision card (matches
    // Today). Neutral/preview carries no accent — the next-session preview stays
    // grey and is never tinted red just because today is a pull-back. The
    // exception is a severe injury: it blocks the scheduled session, so its card
    // IS the blocked one and correctly reads red.
    const decisionTone =
      decisionBanner && decisionBanner.tone !== "neutral" ? decisionBanner.tone : undefined;
    // One dominant next action, resolved from the whole state by a pure helper so
    // the button can never contradict the headline/body (and is unit-tested per
    // state). STOP never falls through to a "train" label — see
    // getOverviewPrimaryAction.
    const primaryAction = getOverviewPrimaryAction({
      hasActivePlan,
      planCount: me.plan_count ?? 0,
      hasInjuryOverride: Boolean(resolvedDecision?.severeInjuryBlocksCurrentSession),
      recommendation,
      decisionTier,
      hasSafeSession: Boolean(safeSession),
    });
    const primaryHref = primaryAction.href;
    const primaryLabel = primaryAction.label === "Open today's session" ? "Today's session" : primaryAction.label;

    return (
      <>
        {/* Primary command area — today's decision, the session it affects, and
            one dominant action lead the first viewport. */}
        <section className="hero-panel overview-command-shell overview-command-primary athlete-motion-slot athlete-motion-header">
          <div className="overview-primary-grid">
            <div className="status-card overview-command-card overview-decision-lead" data-tone={decisionTone}>
              <p className="eyebrow">Today&apos;s command</p>
              <h1 className="hero-title overview-decision-headline">{overviewTitle}</h1>
              <div className="overview-decision-copy">
                {overviewLines.map((line, index) => (
                  <p key={index} className="muted">{line}</p>
                ))}
                {overviewSafety ? <p className="muted overview-decision-safety">{overviewSafety}</p> : null}
              </div>
              <div className="plan-summary-actions overview-primary-actions">
                <Link href={primaryHref} className="cta overview-primary-action">{primaryLabel}</Link>
                {hasActivePlan ? (
                  <Link href={`/plans/${activePlan.id}`} className="secondary-button">Camp plan</Link>
                ) : (
                  <Link href="/quick-build" className="secondary-button">Quick Build</Link>
                )}
              </div>
            </div>
            <div className="overview-primary-session">
              {safeSession ? (
                <article className="status-card overview-command-card overview-safe-session-card" data-tone="red">
                  <p className="status-label">{safeSession.eyebrow}</p>
                  <h2 className="plan-summary-title">{safeSession.title}</h2>
                  <p className="muted">{safeSession.detail}</p>
                  <div className="overview-safe-session-lists">
                    <div className="overview-safe-list" data-kind="allowed">
                      <p className="overview-safe-list-label">Allowed</p>
                      <ul>{safeSession.allowed.map((item) => <li key={item}>{item}</li>)}</ul>
                    </div>
                    <div className="overview-safe-list" data-kind="blocked">
                      <p className="overview-safe-list-label">Blocked</p>
                      <ul>{safeSession.blocked.map((item) => <li key={item}>{item}</li>)}</ul>
                    </div>
                  </div>
                </article>
              ) : showNextPlanned ? (
                <article className="status-card overview-command-card overview-next-session-card">
                  <p className="status-label">Next planned session</p>
                  <h2 className="plan-summary-title">{nextSessionTitle}</h2>
                  {nextSessionDay ? <p className="overview-next-session-day">{nextSessionDay}</p> : null}
                  <p className="overview-session-pending">
                    <span className="overview-pending-pill">Pending</span>
                    Check in on the day to unlock this session.
                  </p>
                  {nextIsHardCombat ? (
                    <div className="overview-caution-row">
                      <span className="overview-caution-label">Caution</span>
                      <span className="overview-caution-text">
                        Combat session planned next. Re-check fatigue, pain, and injury status before clearing.
                      </span>
                    </div>
                  ) : null}
                </article>
              ) : (
                <article className="status-card overview-command-card overview-next-session-card">
                  <p className="status-label">{sessionIsToday ? "Today's session" : "Next session"}</p>
                  <h2 className="plan-summary-title">{nextSessionTitle}</h2>
                  {nextSessionDay ? <p className="overview-next-session-day">{nextSessionDay}</p> : null}
                  {sessionStateLabel ? (
                    <p className="overview-session-state">
                      <span className="overview-session-state-pill">{sessionStateLabel}</span>
                    </p>
                  ) : null}
                  <p className="muted">{nextSessionFocus}</p>
                </article>
              )}
            </div>
          </div>
          {commandError ? (
            <div className="error-banner" role="alert">
              <span>{commandError}</span>
              <button
                type="button"
                className="error-banner-retry"
                onClick={() => void loadCommandState()}
                disabled={isReloadingCommand}
              >
                {isReloadingCommand ? "Retrying..." : "Retry"}
              </button>
            </div>
          ) : null}
        </section>

        {/* Secondary — camp context, progress, full risk watch, disclaimer.
            Available but visually reduced so it never competes with the command. */}
        <section className="panel overview-secondary athlete-motion-slot athlete-motion-status">
          <p className="kicker overview-secondary-eyebrow">{openOngoing ? "Training context" : "Camp context"}</p>
          <div className="overview-operational-strip" aria-label={openOngoing ? "Training status" : "Camp status"}>
            <div className="overview-operational-item"><span className="overview-operational-label">Plan</span><span className="overview-operational-value">{String(activePlan.name || "No active plan")}</span></div>
            <div className="overview-operational-item"><span className="overview-operational-label">{openOngoing ? "Cycle" : "Camp day"}</span><span className="overview-operational-value">{openOngoing ? "Renewable 4-week block" : campDay || "Not set"}</span></div>
            <div className="overview-operational-item"><span className="overview-operational-label">{openOngoing ? "Mode" : "Phase"}</span><span className="overview-operational-value">{openOngoing ? "Ongoing" : humanizeIfRawEnum(activePlan.phase) || "Not set"}</span></div>
            <div className="overview-operational-item"><span className="overview-operational-label">Fight date</span><span className="overview-operational-value">{openOngoing ? "Not scheduled" : formatPlanFightDate(String(activePlan.fight_date || ""))}</span></div>
          </div>
          <CampProgressBar plan={structuredPlan} trainingDay={trainingDay} variant="overview" />
          <OverviewRiskWatch risks={risks} tier={decisionTier} />
        </section>
      </>
    );
  }

  return (
    <>
      <section className="hero-panel public-hero-panel">
        <div className="public-hero-grid">
          <div className="hero-panel-copy public-hero-copy">
            <p className="public-hero-motto" aria-label="Unlxck Your Potential">
              <span>UNLXCK</span>
              <span>Your Potential</span>
            </p>
            <h1 className="hero-title public-hero-title" aria-label="Your camp. Lxcked in.">
              <span>Your camp.</span>
              <span>Lxcked in.</span>
            </h1>
            <p className="public-hero-summary">{PUBLIC_HERO_SUMMARY}</p>
            <div className="hero-actions">
              <Link href="/signup" className="cta">
                Start free beta
              </Link>
              <Link href="/login" className="ghost-button">
                Log in
              </Link>
            </div>
            <div className="public-proof-strip" aria-label="Product outcomes">
              {LANDING_OUTCOME_POINTS.map((point) => (
                <div key={point.label} className="public-proof-pill">
                  <span className="label">{point.label}</span>
                  <span className="public-proof-value">{point.value}</span>
                </div>
              ))}
            </div>
            <InstallUnlxck variant="inline" />
          </div>

          <article className="support-panel public-preview-panel">
            <div className="public-preview-header">
              <div>
                <p className="kicker">Workspace preview</p>
                <h2 className="form-section-title">One app workflow.</h2>
              </div>
              <span className="badge status-badge-neutral">Beta</span>
            </div>
            <div className="public-preview-window">
              <div className="public-preview-toolbar">
                <span className="public-preview-dot public-preview-dot-active" aria-hidden="true" />
                <span className="public-preview-toolbar-label">UNLXCK workspace</span>
              </div>
              <div className="public-preview-shell">
                <aside className="public-preview-sidebar" aria-label="Preview navigation">
                  <span className="public-preview-section-label">Workspace</span>
                  <span className="public-preview-nav-active">Overview</span>
                  <span>Today</span>
                  <span>Plan</span>
                  <span>Intake</span>
                </aside>
              <div className="public-workspace-list">
                {LANDING_WORKSPACE_ROWS.map((row) => (
                  <article key={row.step} className="public-workspace-row">
                    <span className="public-workspace-step">{row.step}</span>
                    <div>
                      <p className="label">{row.label}</p>
                      <h3 className="public-preview-card-title">{row.title}</h3>
                      <p className="muted">{row.body}</p>
                    </div>
                    <span className="public-workspace-status">{row.status}</span>
                  </article>
                ))}
              </div>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section className="public-proof-grid" aria-label="Product proof points">
        {LANDING_PRODUCT_PROOF_POINTS.map((section) => (
          <article key={section.title} className="support-panel public-proof-card">
            <p className="kicker">{section.label}</p>
            <h2 className="form-section-title">{section.title}</h2>
            <p className="muted">{section.body}</p>
          </article>
        ))}
      </section>

      <section className="public-section-break" aria-labelledby="public-journey-heading">
        <div className="public-section-break-line" aria-hidden="true" />
        <div className="public-section-break-copy">
          <p className="kicker">How it works</p>
          <h2 id="public-journey-heading">From setup to review.</h2>
        </div>
        <Image className="public-section-break-logo" src="/unlxck-icon.jpg" alt="" width={72} height={72} aria-hidden="true" />
      </section>

      <section className="metric-grid public-journey-grid">
        {LANDING_WORKFLOW_STEPS.map((step) => (
          <article key={step.title} className="support-panel">
            <div className="form-section-header">
              <p className="kicker">{step.label}</p>
              <h2 className="form-section-title">{step.title}</h2>
            </div>
            <p className="muted">{step.body}</p>
          </article>
        ))}
      </section>

      <section className="public-final-cta" aria-labelledby="public-final-cta-heading">
        <div>
          <p className="kicker">Unlxck Your Potential</p>
          <h2 id="public-final-cta-heading">Build the first camp.</h2>
        </div>
        <div className="hero-actions">
          <Link href="/signup" className="cta">
            Start free beta
          </Link>
          <Link href="/login" className="secondary-button">
            Log in
          </Link>
        </div>
      </section>
    </>
  );
}
