"use client";

import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";

import { useAppSession } from "@/components/auth-provider";
import { CampProgressBar } from "@/components/camp-progress-bar";
import { EmptyState } from "@/components/empty-state";
import { InstallUnlxck } from "@/components/install-unlxck";
import { PlansFeaturedSkeleton, Skeleton } from "@/components/skeleton";
import { XpProgressCard, XpProgressCardSkeleton } from "@/components/xp-progress-card";
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
  getOverviewCommandEyebrow,
  getOverviewPrimaryAction,
  getRiskTimeframeLabel,
  getTierMeta,
  resolveTodayDecision,
} from "@/lib/today";
import type { PlanSummary, StructuredPlan, TodayActivePlan, TodayCommandView } from "@/lib/types";

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
            <XpProgressCardSkeleton />
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
 * Condensed Overview risk index. Today owns the full explanation and action;
 * this card names only the two highest-priority signals and routes overflow to
 * that actionable surface.
 */
function OverviewRiskWatch({ risks = [] }: { risks?: TodayCommandView["risk_watch"] }) {
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

  return (
    <article className="status-card overview-command-card overview-risk-card">
      <p className="status-label">Risk watch</p>
      <div className="overview-risk-list">
        {visible.map((risk, index) => {
          const timeframe = getRiskTimeframeLabel(risk.timeframe);
          const riskLabel = humanizeIfRawEnum(risk.label) || risk.label;
          return (
            <div key={`${risk.category}-${risk.label}-${index}`} className="overview-risk-row" data-tone={risk.tone}>
              <span className="overview-risk-row-label">{timeframe || riskLabel}</span>
              {timeframe ? <span className="overview-risk-row-text">{riskLabel}</span> : null}
            </div>
          );
        })}
      </div>
      {overflow > 0 ? (
        <Link href="/today" className="overview-risk-more">
          Review {overflow} more on Today
        </Link>
      ) : null}
    </article>
  );
}

export default function HomePage() {
  const publicT = useTranslations("PublicHome");
  const landingOutcomePoints = [1, 2, 3].map((index) => ({
    label: publicT(`outcome${index}Label`),
    value: publicT(`outcome${index}Value`),
  }));
  const landingWorkspaceRows = [
    { step: "01", label: publicT("intake"), status: publicT("row1Status"), title: publicT("intake"), body: publicT("row1Body") },
    { step: "02", label: publicT("row2Label"), status: publicT("row2Status"), title: publicT("row2Label"), body: publicT("row2Body") },
    { step: "03", label: publicT("row3Label"), status: publicT("row3Status"), title: publicT("row3Label"), body: publicT("row3Body") },
    { step: "04", label: publicT("today"), status: publicT("row4Status"), title: publicT("today"), body: publicT("row4Body") },
  ];
  const landingProductProofPoints = [
    { label: publicT("today"), title: publicT("proof1Title"), body: publicT("proof1Body") },
    { label: publicT("row2Label"), title: publicT("proof2Title"), body: publicT("proof2Body") },
    { label: publicT("proof3Label"), title: publicT("proof3Title"), body: publicT("proof3Body") },
  ];
  const landingWorkflowSteps = [1, 2, 3, 4].map((index) => ({
    label: publicT(`step${index}Label`),
    title: publicT(`step${index}Title`),
    body: publicT(`step${index}Body`),
  }));
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
            <InstallUnlxck variant="inline" />
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
    const resolvedDecision = commandState ? resolveTodayDecision(commandState) : null;
    const risks = commandState?.risk_watch ?? [];
    const recommendation = commandState?.today?.recommendation_state ?? "not_checked_in";
    // Overview consumes the same authoritative resolver as Today. The backend
    // tier controls safety; structured severe-injury data only supplies truthful
    // STOP presentation and the injury check-in action.
    const decisionBanner = resolvedDecision?.banner ?? null;
    const decisionTier = resolvedDecision?.displayTier ?? "not_checked_in";
    const tierMeta = getTierMeta(decisionTier);
    const safetyNoticeLeads = resolvedDecision?.primaryMessageKind === "safety_notice";
    const decisionTitle = safetyNoticeLeads
      ? decisionBanner?.title ?? "Current safety"
      : tierMeta.label;
    const overviewEyebrow = safetyNoticeLeads
      ? "Current safety"
      : getOverviewCommandEyebrow(decisionTier);
    const decisionLines = decisionBanner
      ? (safetyNoticeLeads
          ? [decisionBanner.action, decisionBanner.detail]
          : [decisionBanner.detail, decisionBanner.action]
        ).filter((line): line is string => Boolean(line))
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
      hasSafeSession: Boolean(resolvedDecision?.useSafeReplacement),
      sessionIsToday,
    });
    const primaryHref = primaryAction.href;
    const primaryLabel = primaryAction.label;

    return (
      <>
        {/* Primary command area — today's decision, the session it affects, and
            one dominant action lead the first viewport. */}
        <section className="hero-panel overview-command-shell overview-command-primary athlete-motion-slot athlete-motion-header">
          <div className="overview-primary-grid">
            <div className="status-card overview-command-card overview-decision-lead" data-tone={decisionTone}>
              <p className="eyebrow">{overviewEyebrow}</p>
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
              <XpProgressCard />
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
          <OverviewRiskWatch risks={risks} />
        </section>
      </>
    );
  }

  return (
    <>
      <section className="hero-panel public-hero-panel">
        <div className="public-hero-grid">
          <div className="hero-panel-copy public-hero-copy">
            <p className="public-hero-motto" aria-label={publicT("motto")}>
              <span>UNLXCK</span>
              <span>{publicT("motto").replace(/^UNLXCK\s+/i, "")}</span>
            </p>
            <h1 className="hero-title public-hero-title" aria-label={publicT("heroTitle")}>
              <span>{publicT("heroLine1")}</span>
              <span>{publicT("heroLine2")}</span>
            </h1>
            <p className="public-hero-lead">{publicT("lead")}</p>
            <p className="public-hero-summary">{publicT("summary")}</p>
            <div className="hero-actions public-hero-actions">
              <Link href="/signup" className="cta">
                {publicT("getStarted")}
              </Link>
              <Link href="/login" className="ghost-button">
                {publicT("login")}
              </Link>
            </div>
            <p className="public-hero-cta-note">{publicT("betaNote")}</p>
            <div className="public-proof-strip" aria-label={publicT("productOutcomes")}>
              {landingOutcomePoints.map((point) => (
                <div key={point.label} className="public-proof-pill">
                  <span className="label">{point.label}</span>
                  <span className="public-proof-value">{point.value}</span>
                </div>
              ))}
            </div>
          </div>

          <article className="support-panel public-preview-panel">
            <div className="public-preview-header">
              <div>
                <p className="kicker">{publicT("workspacePreview")}</p>
                <h2 className="form-section-title">{publicT("previewTitle")}</h2>
              </div>
              <span className="badge status-badge-neutral">{publicT("beta")}</span>
            </div>
            <div className="public-preview-window">
              <div className="public-preview-toolbar">
                <span className="public-preview-dot public-preview-dot-active" aria-hidden="true" />
                <span className="public-preview-toolbar-label">{publicT("workspaceLabel")}</span>
              </div>
              <div className="public-preview-shell">
                <aside className="public-preview-sidebar" aria-label={publicT("previewNavigation")}>
                  <span className="public-preview-section-label">{publicT("workspace")}</span>
                  <span className="public-preview-nav-active">{publicT("overview")}</span>
                  <span>{publicT("today")}</span>
                  <span>{publicT("plan")}</span>
                  <span>{publicT("intake")}</span>
                </aside>
              <div className="public-workspace-list">
                <article className="public-today-preview" aria-label="Today, modified session">
                  <div className="public-today-preview-head">
                      <span className="public-today-preview-eyebrow">{publicT("today")}</span>
                      <span className="public-today-preview-status">{publicT("modifiedSession")}</span>
                  </div>
                  <ul className="public-today-changes">
                    {([
                      { direction: "down" as const, text: publicT("heavyBagReduced") },
                      { direction: "up" as const, text: publicT("reactionDrillsIncreased") },
                    ]).map((change) => (
                      <li
                        key={change.text}
                        className="public-today-change"
                        data-direction={change.direction}
                      >
                        <span className="public-today-change-glyph" aria-hidden="true">
                          {change.direction === "up" ? "↑" : "↓"}
                        </span>
                        <span className="public-today-change-text">{change.text}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="public-today-reason">
                    <span className="public-today-reason-label">{publicT("reason")}</span>
                    <span>{publicT("highFatigue")}</span>
                  </p>
                </article>
                {landingWorkspaceRows.map((row) => (
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

      <section className="public-proof-grid" aria-label={publicT("productProof")}>
        {landingProductProofPoints.map((section) => (
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
          <p className="kicker">{publicT("howItWorks")}</p>
          <h2 id="public-journey-heading">{publicT("journeyTitle")}</h2>
        </div>
        <Image
          className="public-section-break-logo"
          src="/brand/unlxck-codex-icon-upgrade/assets/brand/unlxck-mark-120.png"
          alt=""
          width={72}
          height={72}
          aria-hidden="true"
        />
      </section>

      <section className="metric-grid public-journey-grid">
        {landingWorkflowSteps.map((step) => (
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
          <p className="kicker">{publicT("potential")}</p>
          <h2 id="public-final-cta-heading">{publicT("finalTitle")}</h2>
        </div>
        <div className="hero-actions">
          <Link href="/signup" className="cta">
            {publicT("getStarted")}
          </Link>
          <Link href="/login" className="secondary-button">
            {publicT("login")}
          </Link>
        </div>
      </section>
    </>
  );
}
