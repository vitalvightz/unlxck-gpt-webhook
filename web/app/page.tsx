"use client";

import Link from "next/link";
import { type ReactNode, useEffect, useState } from "react";

import { useAppSession } from "@/components/auth-provider";
import { listPlans } from "@/lib/api";
import {
  getOptionLabel,
  PROFESSIONAL_STATUS_OPTIONS,
  STANCE_OPTIONS,
  TACTICAL_STYLE_OPTIONS,
  TECHNICAL_STYLE_OPTIONS,
} from "@/lib/intake-options";
import { formatPlanFightDate, formatPlanTimestamp, getPlanDisplayName } from "@/lib/plan-format";
import type { PlanSummary } from "@/lib/types";

const demoMode = process.env.NEXT_PUBLIC_DEMO_MODE === "1";

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

export default function HomePage() {
  const { isReady, session, me } = useAppSession();
  const [recentPlans, setRecentPlans] = useState<PlanSummary[]>([]);

  useEffect(() => {
    let active = true;

    const fallbackPlans = me?.latest_plan ? [me.latest_plan] : [];

    if (!session?.access_token || !me) {
      setRecentPlans(fallbackPlans);
      return () => {
        active = false;
      };
    }

    if (me.plan_count <= 1) {
      setRecentPlans(fallbackPlans);
      return () => {
        active = false;
      };
    }

    setRecentPlans(fallbackPlans);

    void listPlans(session.access_token)
      .then((plans) => {
        if (!active) {
          return;
        }
        setRecentPlans(plans.slice(0, 2));
      })
      .catch(() => {
        if (!active) {
          return;
        }
        setRecentPlans(fallbackPlans);
      });

    return () => {
      active = false;
    };
  }, [me?.latest_plan?.plan_id, me?.plan_count, session?.access_token]);

  if (!isReady) {
    return (
      <section className="panel loading-card">
        <p className="kicker">Overview</p>
        <h1>Loading your athlete workspace</h1>
        <p className="muted">Checking saved onboarding and plan history.</p>
      </section>
    );
  }

  if (session && me) {
    const latestPlan = me.latest_plan ?? null;
    const draft = (me.profile.onboarding_draft as { current_step?: number } | null) ?? null;
    const latestIntake = me.latest_intake;
    const nextStepNumber = Number.isFinite(Number(draft?.current_step ?? 0)) ? Number(draft?.current_step ?? 0) + 1 : 1;
    const totalOnboardingSteps = 6;
    const remainingSteps = draft ? Math.max(totalOnboardingSteps - nextStepNumber, 0) : totalOnboardingSteps;
    const progressValue = draft ? (nextStepNumber / totalOnboardingSteps) * 100 : 0;
    const displayedPlans = recentPlans.length ? recentPlans : latestPlan ? [latestPlan] : [];
    const fightDate = latestIntake?.fight_date || latestPlan?.fight_date || null;
    const primaryStyle = getOptionLabel(TECHNICAL_STYLE_OPTIONS, me.profile.technical_style[0] ?? "") || "Not provided";
    const tacticalStyle = getOptionLabel(TACTICAL_STYLE_OPTIONS, me.profile.tactical_style[0] ?? "") || "Not provided";
    const stance = getOptionLabel(STANCE_OPTIONS, me.profile.stance ?? "") || "Not provided";
    const status = getOptionLabel(PROFESSIONAL_STATUS_OPTIONS, me.profile.professional_status ?? "") || "Not provided";
    const readinessBadge = draft ? "In progress" : "Ready to start";
    const nextActionSummary = latestPlan
      ? `Latest plan saved ${formatPlanTimestamp(latestPlan.created_at)}.`
      : draft
        ? `Draft is parked on step ${nextStepNumber} of 6.`
        : "Profile is ready for the first intake.";
    const primaryActionHref = latestPlan ? `/plans/${latestPlan.plan_id}` : "/onboarding";
    const primaryActionLabel = latestPlan ? "Open latest plan" : draft ? "Resume onboarding" : "Start onboarding";
    const primaryActionTitle = latestPlan ? "Open current plan" : draft ? "Finish onboarding" : "Start onboarding";
    const operationalItems = [
      { label: "Latest update", value: latestPlan ? formatPlanTimestamp(latestPlan.created_at) : formatPlanTimestamp(me.profile.updated_at) },
      { label: "Fight date", value: formatPlanFightDate(fightDate) },
      { label: "Primary style", value: primaryStyle },
    ];
    const decisionItems = [
      {
        label: "Onboarding",
        value: draft ? `Step ${nextStepNumber} of ${totalOnboardingSteps}` : "Not started",
      },
      { label: "Saved plans", value: formatPlanCount(me.plan_count) },
      { label: "Fight date", value: formatPlanFightDate(fightDate) },
    ];
    const profileStateItems = [
      { label: "Full name", value: me.profile.full_name || "Not provided" },
      { label: "Technical style", value: primaryStyle },
      { label: "Tactical style", value: tacticalStyle },
      { label: "Stance", value: stance },
      { label: "Status", value: status },
      { label: "Record", value: me.profile.record || "Not provided" },
      {
        label: "Onboarding progress",
        value: draft ? `Step ${nextStepNumber} of ${totalOnboardingSteps}` : "Not started",
        highlight: true,
        badgeText: readinessBadge,
        helperText: draft
          ? remainingSteps === 0
            ? "All onboarding steps are complete."
            : `${remainingSteps} step${remainingSteps === 1 ? "" : "s"} remaining before plan generation.`
          : "Start onboarding to unlock guided plan generation.",
        progressValue,
      },
    ];

    return (
      <>
        <section className="hero-panel overview-command-shell athlete-motion-slot athlete-motion-header">
          <div className="overview-command-grid">
            <div className="hero-panel-copy overview-command-copy">
              <p className="eyebrow">Overview</p>
              <h1 className="hero-title">One workspace, one clear next step.</h1>
              <p className="overview-command-summary">Pick up the latest camp action first, then open profile detail and history only when you need them.</p>
              <div className="overview-operational-strip" aria-label="Workspace status">
                {operationalItems.map((item) => (
                  <div key={item.label} className="overview-operational-item">
                    <span className="overview-operational-label">{item.label}</span>
                    <span className="overview-operational-value">{item.value}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="status-card overview-next-action overview-decision-card">
              <p className="status-label">Next action</p>
              <h2 className="plan-summary-title">{primaryActionTitle}</h2>
              <div className="overview-next-action-state">
                <span className={latestPlan ? "badge" : "badge status-badge-neutral"}>{latestPlan ? latestPlan.status : "Onboarding"}</span>
                <p className="muted">{nextActionSummary}</p>
              </div>
              <div className="overview-decision-strip" aria-label="Next step details">
                {decisionItems.map((item) => (
                  <div key={item.label} className="overview-decision-item">
                    <span className="overview-operational-label">{item.label}</span>
                    <span className="overview-operational-value">{item.value}</span>
                  </div>
                ))}
              </div>
              <div className="plan-summary-actions">
                <Link href={primaryActionHref} className="cta overview-primary-action">
                  {primaryActionLabel}
                </Link>
              </div>
            </div>
          </div>

          <div className="overview-disclosure-stack athlete-motion-slot athlete-motion-status">
            <OverviewDisclosure
              title="Profile snapshot"
              summary={draft ? `Onboarding is ${remainingSteps === 0 ? "ready for review" : `still ${remainingSteps} step${remainingSteps === 1 ? "" : "s"} away`}.` : "Profile fields currently saved for the next plan."}
              badge={readinessBadge}
            >
              <OverviewDetailGrid items={profileStateItems} />
              <div className="plan-card-actions overview-card-actions">
                <Link href="/onboarding" className="secondary-button">
                  {draft ? "Resume onboarding" : "Start onboarding"}
                </Link>
                <Link href="/settings" className="ghost-button">
                  Update settings
                </Link>
              </div>
            </OverviewDisclosure>

            <OverviewDisclosure
              title="Recent plans"
              summary={displayedPlans.length ? `${displayedPlans.length === 1 ? "1 saved plan is ready to reopen." : `${displayedPlans.length} recent plans are ready to reopen.`}` : "No plans yet. Finish onboarding to create the first one."}
              badge={formatPlanCount(me.plan_count)}
            >
              {displayedPlans.length ? (
                <div className="plan-history-list">
                  {displayedPlans.map((plan, index) => (
                    <article key={plan.plan_id} className="plan-history-row overview-history-row">
                      <div className="plan-history-copy">
                        <p className="label">{index === 0 ? "Latest saved plan" : "Recent saved plan"}</p>
                        <h3 className="plan-card-title">{getPlanDisplayName(plan)}</h3>
                        <p className="overview-history-meta-line">Created {formatPlanTimestamp(plan.created_at)}</p>
                      </div>
                      <div className="plan-history-meta">
                        <span className="badge">{plan.status}</span>
                        <Link href={`/plans/${plan.plan_id}`} className="ghost-button overview-history-action">
                          Open plan
                        </Link>
                      </div>
                    </article>
                  ))}
                  <div className="plan-card-actions overview-card-actions">
                    <Link href="/plans" className="ghost-button">
                      View full history
                    </Link>
                  </div>
                </div>
              ) : (
                <div className="support-panel">
                  <p className="kicker">No plans yet</p>
                  <p className="muted">Finish onboarding to create your first saved fight camp.</p>
                </div>
              )}
            </OverviewDisclosure>
          </div>
        </section>
      </>
    );
  }

  return (
    <>
      <section className="hero-panel">
        <div className="hero-panel-copy">
          <p className="eyebrow">Athlete-first beta</p>
          <h1 className="hero-title">Get your fight camp on the web.</h1>
          <p>UNLXCK brings onboarding, generation, history, and exports into one athlete workspace.</p>
        </div>
        <div className="hero-actions">
          <Link href="/signup" className="cta">
            Start free beta
          </Link>
          <Link href="/login" className="ghost-button">
            Log in
          </Link>
          {demoMode ? (
            <Link href="/login" className="ghost-button">
              Try demo
            </Link>
          ) : null}
        </div>
      </section>

      <section className="metric-grid">
        <article className="support-panel">
          <div className="form-section-header">
            <p className="kicker">Step 1</p>
            <h2 className="form-section-title">Sign up</h2>
          </div>
          <p className="muted">Create an athlete account and keep plan history in one place.</p>
        </article>
        <article className="support-panel">
          <div className="form-section-header">
            <p className="kicker">Step 2</p>
            <h2 className="form-section-title">Onboard</h2>
          </div>
          <p className="muted">Complete the structured intake inside the product.</p>
        </article>
        <article className="support-panel">
          <div className="form-section-header">
            <p className="kicker">Step 3</p>
            <h2 className="form-section-title">Generate</h2>
          </div>
          <p className="muted">Turn that intake into a saved fight camp plan.</p>
        </article>
      </section>
    </>
  );
}
