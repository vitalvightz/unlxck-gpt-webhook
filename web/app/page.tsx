"use client";

import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";

import { useAppSession } from "@/components/auth-provider";
import { EmptyState } from "@/components/empty-state";
import { PlansFeaturedSkeleton, Skeleton } from "@/components/skeleton";
import { getToday } from "@/lib/api";
import {
  getOptionLabel,
  PROFESSIONAL_STATUS_OPTIONS,
  STANCE_OPTIONS,
  TACTICAL_STYLE_OPTIONS,
  TECHNICAL_STYLE_OPTIONS,
} from "@/lib/intake-options";
import { humanizeIfRawEnum } from "@/lib/plan-labels";
import { formatAppDate } from "@/lib/date-format";
import { formatPlanFightDate, formatPlanTimestamp, getPlanDisplayName } from "@/lib/plan-format";
import {
  getSessionDayLabel,
  getSessionFocus,
  getSessionTitle,
  hasTodaySession,
} from "@/lib/today";
import type { PlanSummary, TodayActivePlan, TodayCommandView, TodaySession } from "@/lib/types";

const landingWorkspaceRows = [
  {
    step: "01",
    label: "Intake",
    status: "Complete",
    title: "Intake",
    body: "Fight date, schedule, style, goals, and restrictions.",
  },
  {
    step: "02",
    label: "Readiness",
    status: "Checked",
    title: "Readiness",
    body: "Load, nutrition, injuries, and availability.",
  },
  {
    step: "03",
    label: "Camp Plan",
    status: "Ready",
    title: "Camp plan",
    body: "Phases, sessions, targets, and recovery.",
  },
  {
    step: "04",
    label: "Saved History",
    status: "Saved",
    title: "History",
    body: "Latest camp and past plans stay attached.",
  },
] as const;

const landingOutcomePoints = [
  {
    label: "Intake",
    value: "Context and limits",
  },
  {
    label: "Readiness",
    value: "Load and safety",
  },
  {
    label: "Camp Plan",
    value: "Weeks and sessions",
  },
  {
    label: "Saved History",
    value: "Plans attached",
  },
] as const;

const landingWorkflowSteps = [
  {
    label: "Step 1",
    title: "Complete intake",
    body: "Add fight context, availability, restrictions, history, and goals.",
  },
  {
    label: "Step 2",
    title: "Run readiness check",
    body: "Check load, nutrition, injuries, and schedule limits.",
  },
  {
    label: "Step 3",
    title: "Generate fight camp",
    body: "Create phases, sessions, targets, and key performance work.",
  },
  {
    label: "Step 4",
    title: "Return between sessions",
    body: "Reopen, review, and continue on mobile or desktop.",
  },
] as const;

const landingProductProofPoints = [
  {
    label: "Intake",
    title: "Context before output.",
    body: "Fight date, schedule, style, training age, equipment, restrictions, and goals.",
  },
  {
    label: "Readiness",
    title: "Constraints stay visible.",
    body: "Load, recovery, nutrition, injury limits, and availability stay beside the plan.",
  },
  {
    label: "Camp Plan",
    title: "The plan is structured.",
    body: "Phases, daily sessions, conditioning, strength, recovery, and targets.",
  },
  {
    label: "Saved History",
    title: "Return without rebuilding.",
    body: "Latest camp and previous plans stay attached for review and continuation.",
  },
] as const;

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
    <section className="hero-panel overview-command-shell athlete-motion-slot athlete-motion-header" aria-busy="true">
      <div className="overview-command-grid">
        <div className="hero-panel-copy overview-command-copy">
          <Skeleton variant="text" width={90} height={12} />
          <Skeleton variant="text" width="68%" height={42} />
          <Skeleton variant="text" width="82%" height={16} />
          <div className="overview-operational-strip" aria-label="Workspace status loading">
            {[0, 1, 2].map((index) => (
              <div key={index} className="overview-operational-item">
                <Skeleton variant="text" width={92} height={10} />
                <Skeleton variant="text" width={136} height={16} />
              </div>
            ))}
          </div>
        </div>
        <PlansFeaturedSkeleton />
      </div>
      <div className="overview-disclosure-stack athlete-motion-slot athlete-motion-status">
        <PlansFeaturedSkeleton />
      </div>
    </section>
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

export default function HomePage() {
  const { isReady, isMeHydrated, hasTransientMeError, session, me, signOut, refreshMe } = useAppSession();
  const router = useRouter();
  const [commandState, setCommandState] = useState<TodayCommandView | null>(null);
  const [commandError, setCommandError] = useState<string | null>(null);

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
    const sessionPreview = (commandState?.today?.next_session ?? {}) as TodaySession;
    const hasNextSession = hasTodaySession(sessionPreview);
    const nextSessionTitle = hasNextSession ? getSessionTitle(sessionPreview) : "No upcoming session";
    const nextSessionDay = hasNextSession ? getSessionDayLabel(sessionPreview) : "";
    const nextSessionFocus = hasNextSession
      ? getSessionFocus(sessionPreview)
      : hasActivePlan
        ? "Open Today for the matched session."
        : "Generate a plan to see your next session.";
    const risks = commandState?.risk_watch ?? [];
    const visibleRisks = risks.slice(0, 2);
    const riskOverflow = Math.max(0, risks.length - visibleRisks.length);
    const recommendation = commandState?.today?.recommendation_state ?? "not_checked_in";
    const todayStateLabel = recommendation === "train_as_planned"
      ? "Train as planned"
      : recommendation === "modify"
        ? "Modify today"
        : recommendation === "pull_back"
          ? "Pull back today"
          : "Check in required";
    // Decision tone drives the colour accents on the command cards (matches Today).
    const decisionTone =
      recommendation === "train_as_planned"
        ? "green"
        : recommendation === "modify"
          ? "amber"
          : recommendation === "pull_back"
            ? "red"
            : undefined;
    const primaryHref = hasActivePlan ? "/today" : "/onboarding";
    const primaryLabel = hasActivePlan ? (recommendation === "not_checked_in" ? "Open Today / Check in" : "Open Today") : "Complete Intake";

    return (
      <>
        <section className="hero-panel overview-command-shell athlete-motion-slot athlete-motion-header">
          <div className="overview-command-grid">
            <div className="hero-panel-copy overview-command-copy">
              <p className="eyebrow">Overview</p>
              <h1 className="hero-title">Camp command centre</h1>
              <p className="overview-command-summary">Today&apos;s training decision, next target, and risk watch from the active camp plan.</p>
              <div className="overview-operational-strip" aria-label="Camp status">
                <div className="overview-operational-item"><span className="overview-operational-label">Active plan</span><span className="overview-operational-value">{String(activePlan.name || "No active plan")}</span></div>
                <div className="overview-operational-item"><span className="overview-operational-label">Phase</span><span className="overview-operational-value">{humanizeIfRawEnum(activePlan.phase) || "Not set"}</span></div>
                <div className="overview-operational-item"><span className="overview-operational-label">Training day</span><span className="overview-operational-value">{commandState?.today?.training_day ? formatAppDate(commandState.today.training_day) : "Not set"}</span></div>
                <div className="overview-operational-item"><span className="overview-operational-label">Fight date</span><span className="overview-operational-value">{formatPlanFightDate(String(activePlan.fight_date || ""))}</span></div>
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
            </div>
            <div className="status-card overview-next-action overview-decision-card overview-command-card" data-tone={decisionTone}>
              <p className="status-label">Today&apos;s state</p>
              <h2 className="plan-summary-title">{todayStateLabel}</h2>
              <p className="muted">{commandState?.today?.recommendation_reason || "Open Today for the current decision and session log."}</p>
              <div className="plan-summary-actions">
                <Link href={primaryHref} className="cta overview-primary-action">{primaryLabel}</Link>
                {hasActivePlan ? (
                  <Link href={`/plans/${activePlan.id}`} className="secondary-button">View full plan</Link>
                ) : (
                  <Link href="/quick-build" className="secondary-button">Quick Build</Link>
                )}
              </div>
            </div>
          </div>

          <div className="overview-disclosure-stack athlete-motion-slot athlete-motion-status">
            <article className="status-card overview-command-card overview-next-session-card" data-tone={decisionTone}>
              <p className="status-label">Next session</p>
              <h2 className="plan-summary-title">{nextSessionTitle}</h2>
              {nextSessionDay ? <p className="overview-next-session-day">{nextSessionDay}</p> : null}
              <p className="muted">{nextSessionFocus}</p>
            </article>
            <article className="status-card overview-command-card overview-risk-card">
              <p className="status-label">Risk watch</p>
              {visibleRisks.length ? visibleRisks.map((risk) => (
                <div key={`${risk.category}-${risk.label}`} className="overview-risk-row" data-tone={risk.tone}>
                  <span className="overview-risk-row-label">{humanizeIfRawEnum(risk.label) || risk.label}</span>
                  <span className="overview-risk-row-text">{risk.text || "Monitor before training."}</span>
                </div>
              )) : <p className="muted">No risk flags from today&apos;s command view.</p>}
              {riskOverflow ? <span className="badge status-badge-neutral">+{riskOverflow} more</span> : null}
            </article>
          </div>
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
            <p className="public-hero-summary">Intake, readiness, camp plan, and saved history in one workspace.</p>
            <div className="hero-actions">
              <Link href="/signup" className="cta">
                Start free beta
              </Link>
              <Link href="/login" className="ghost-button">
                Log in
              </Link>
            </div>
            <div className="public-proof-strip" aria-label="Product outcomes">
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

      <section className="public-proof-grid" aria-label="Product proof points">
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
          <p className="kicker">How it works</p>
          <h2 id="public-journey-heading">From setup to review.</h2>
        </div>
        <Image className="public-section-break-logo" src="/unlxck-icon.png" alt="" width={72} height={72} aria-hidden="true" />
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
