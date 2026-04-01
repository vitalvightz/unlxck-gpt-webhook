"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useAppSession } from "@/components/auth-provider";
import { listPlans } from "@/lib/api";
import {
  getOptionLabel,
  PROFESSIONAL_STATUS_OPTIONS,
  STANCE_OPTIONS,
  TACTICAL_STYLE_OPTIONS,
  TECHNICAL_STYLE_OPTIONS,
} from "@/lib/intake-options";
import type { PlanSummary } from "@/lib/types";

const demoMode = process.env.NEXT_PUBLIC_DEMO_MODE === "1";

function getPlanDisplayName(plan: { plan_name?: string | null; fight_date?: string | null }) {
  return plan.plan_name?.trim() || plan.fight_date || "Open saved plan";
}

function formatTimestamp(value?: string | null): string {
  if (!value) {
    return "Not available";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

function formatFightDate(value?: string | null): string {
  if (!value) {
    return "Not provided";
  }

  const parsed = new Date(`${value}T12:00:00Z`);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(parsed);
}

function formatPlanCount(value: number): string {
  return `${value} saved plan${value === 1 ? "" : "s"}`;
}

function OverviewDetailList({
  items,
}: {
  items: Array<{ label: string; value: string; highlight?: boolean; badgeText?: string }>;
}) {
  return (
    <div className="review-detail-list overview-detail-list">
      {items.map((item) => (
        <div
          key={`${item.label}-${item.value}`}
          className={item.highlight ? "review-detail-row overview-detail-row-highlight" : "review-detail-row"}
        >
          <div className="overview-detail-heading">
            <p className="review-detail-label">{item.label}</p>
            {item.badgeText ? <span className="overview-inline-badge">{item.badgeText}</span> : null}
          </div>
          <p className={item.highlight ? "review-detail-value overview-detail-value-strong" : "review-detail-value"}>{item.value}</p>
        </div>
      ))}
    </div>
  );
}

function OverviewDetailGrid({
  items,
}: {
  items: Array<{ label: string; value: string; highlight?: boolean; badgeText?: string }>;
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
    const displayedPlans = recentPlans.length ? recentPlans : latestPlan ? [latestPlan] : [];
    const fightDate = latestIntake?.fight_date || latestPlan?.fight_date || null;
    const primaryStyle = getOptionLabel(TECHNICAL_STYLE_OPTIONS, me.profile.technical_style[0] ?? "") || "Not provided";
    const tacticalStyle = getOptionLabel(TACTICAL_STYLE_OPTIONS, me.profile.tactical_style[0] ?? "") || "Not provided";
    const stance = getOptionLabel(STANCE_OPTIONS, me.profile.stance ?? "") || "Not provided";
    const status = getOptionLabel(PROFESSIONAL_STATUS_OPTIONS, me.profile.professional_status ?? "") || "Not provided";
    const readinessBadge = draft ? "In progress" : "Ready to start";
    const nextActionSummary = latestPlan
      ? `Latest plan saved ${formatTimestamp(latestPlan.created_at)}.`
      : draft
        ? `Draft is parked on step ${nextStepNumber} of 6.`
        : "Profile is ready for the first intake.";
    const operationalItems = [
      { label: "Latest update", value: latestPlan ? formatTimestamp(latestPlan.created_at) : formatTimestamp(me.profile.updated_at) },
      { label: "Fight date", value: formatFightDate(fightDate) },
      { label: "History", value: formatPlanCount(me.plan_count) },
    ];
    const profileStateItems = [
      { label: "Full name", value: me.profile.full_name || "Not provided" },
      { label: "Technical style", value: primaryStyle },
      { label: "Tactical style", value: tacticalStyle },
      { label: "Stance", value: stance },
      { label: "Status", value: status },
      { label: "Record", value: me.profile.record || "Not provided" },
      { label: "Draft step", value: draft ? `${nextStepNumber} / 6` : "Not started", highlight: true, badgeText: readinessBadge },
    ];

    return (
      <>
        <section className="hero-panel overview-command-shell athlete-motion-slot athlete-motion-header">
          <div className="overview-command-grid">
            <div className="hero-panel-copy overview-command-copy">
              <p className="eyebrow">Overview</p>
              <h1 className="hero-title">Control the full camp from one athlete workspace.</h1>
              <p className="overview-command-summary">Resume onboarding, generate a plan, and reopen past camps in one place.</p>
              <div className="overview-operational-strip" aria-label="Workspace status">
                {operationalItems.map((item) => (
                  <div key={item.label} className="overview-operational-item">
                    <span className="overview-operational-label">{item.label}</span>
                    <span className="overview-operational-value">{item.value}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="status-card overview-next-action">
              <p className="status-label">Next action</p>
              <h2 className="plan-summary-title">{latestPlan ? "Open current plan" : "Finish onboarding"}</h2>
              <div className="overview-next-action-state">
                <span className={latestPlan ? "badge" : "badge status-badge-neutral"}>{latestPlan ? latestPlan.status : "Onboarding"}</span>
                <p className="muted">{nextActionSummary}</p>
              </div>
              <div className="plan-summary-actions">
                <Link href={latestPlan ? `/plans/${latestPlan.plan_id}` : "/onboarding"} className="cta overview-primary-action">
                  {latestPlan ? "Open latest plan" : "Resume onboarding"}
                </Link>
                <Link href="/plans" className="ghost-button overview-secondary-action">
                  View history
                </Link>
              </div>
            </div>
          </div>

          <div className="overview-snapshot-strip athlete-motion-slot athlete-motion-status">
            <article className="overview-snapshot-item">
              <p className="kicker">Saved plans</p>
              <p className="overview-snapshot-value">{me.plan_count}</p>
              <p className="muted">All generations stay in history.</p>
            </article>
            <article className="overview-snapshot-item">
              <p className="kicker">Primary style</p>
              <p className="overview-snapshot-value">{primaryStyle}</p>
              <p className="muted">Pulled from the athlete profile.</p>
            </article>
            <article className="overview-snapshot-item">
              <p className="kicker">Fight date</p>
              <p className="overview-snapshot-value">{formatFightDate(fightDate)}</p>
              <p className="muted">Using the latest saved intake.</p>
            </article>
          </div>
        </section>

        <section className="overview-grid overview-dashboard-grid">
          <article className="list-card overview-card athlete-motion-slot athlete-motion-main">
            <div className="overview-card-header">
              <p className="kicker">Onboarding</p>
              <h2>Current profile state</h2>
              <p className="muted">Plan-facing fields currently saved to this athlete profile.</p>
            </div>
            <div className="overview-card-body">
              <OverviewDetailGrid items={profileStateItems} />
              <div className="plan-card-actions overview-card-actions">
                <Link href="/onboarding" className="secondary-button">
                  {draft ? "Resume onboarding" : "Start onboarding"}
                </Link>
                <Link href="/settings" className="ghost-button">
                  Update settings
                </Link>
              </div>
            </div>
          </article>

          <article className="list-card overview-card athlete-motion-slot athlete-motion-rail">
            <div className="overview-card-header">
              <p className="kicker">History</p>
              <h2>Recent plans</h2>
              <p className="muted">Latest saved camps ready to reopen fast.</p>
            </div>
            <div className="overview-card-body">
              {displayedPlans.length ? (
                <div className="plan-history-list">
                  {displayedPlans.map((plan, index) => (
                    <article key={plan.plan_id} className="plan-history-row overview-history-row">
                      <div className="plan-history-copy">
                        <p className="label">{index === 0 ? "Latest saved plan" : "Recent saved plan"}</p>
                        <h3 className="plan-card-title">{getPlanDisplayName(plan)}</h3>
                        <p className="overview-history-meta-line">Created {formatTimestamp(plan.created_at)}</p>
                      </div>
                      <div className="plan-history-meta">
                        <span className="badge">{plan.status}</span>
                        <Link href={`/plans/${plan.plan_id}`} className="ghost-button overview-history-action">
                          Open plan
                        </Link>
                      </div>
                    </article>
                  ))}
                  {me.plan_count > displayedPlans.length ? (
                    <p className="muted">
                      + {me.plan_count - displayedPlans.length} earlier saved plan{me.plan_count - displayedPlans.length === 1 ? "" : "s"} in history.
                    </p>
                  ) : null}
                </div>
              ) : (
                <div className="support-panel">
                  <p className="kicker">No plans yet</p>
                  <p className="muted">Finish onboarding to create your first saved fight camp.</p>
                  <div className="plan-card-actions">
                    <Link href="/onboarding" className="cta inline-cta">
                      Start onboarding
                    </Link>
                  </div>
                </div>
              )}
            </div>
          </article>
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
