"use client";

import Link from "next/link";

import { useAppSession } from "@/components/auth-provider";
import {
  getOptionLabel,
  PROFESSIONAL_STATUS_OPTIONS,
  STANCE_OPTIONS,
  TACTICAL_STYLE_OPTIONS,
  TECHNICAL_STYLE_OPTIONS,
} from "@/lib/intake-options";

const demoMode = process.env.NEXT_PUBLIC_DEMO_MODE === "1";

function sortPlansByCreatedAt<T extends { created_at: string }>(plans: T[]): T[] {
  return [...plans].sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime());
}

function getPlanDisplayName(plan: { plan_name?: string | null; fight_date?: string | null }) {
  return plan.plan_name?.trim() || plan.fight_date || "Open saved plan";
}

function OverviewDetailList({ items }: { items: Array<{ label: string; value: string }> }) {
  return (
    <div className="review-detail-list">
      {items.map((item) => (
        <div key={`${item.label}-${item.value}`} className="review-detail-row">
          <p className="review-detail-label">{item.label}</p>
          <p className="review-detail-value">{item.value}</p>
        </div>
      ))}
    </div>
  );
}

function OverviewDetailGrid({ items }: { items: Array<{ label: string; value: string }> }) {
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
    const plans = sortPlansByCreatedAt(me.plans);
    const latestPlan = plans[0] ?? null;
    const draft = (me.profile.onboarding_draft as { current_step?: number } | null) ?? null;
    const latestIntake = me.latest_intake;
    const nextStepNumber = Number.isFinite(Number(draft?.current_step ?? 0)) ? Number(draft?.current_step ?? 0) + 1 : 1;
    const primaryStyle = getOptionLabel(TECHNICAL_STYLE_OPTIONS, me.profile.technical_style[0] ?? "") || "Not provided";
    const tacticalStyle = getOptionLabel(TACTICAL_STYLE_OPTIONS, me.profile.tactical_style[0] ?? "") || "Not provided";
    const stance = getOptionLabel(STANCE_OPTIONS, me.profile.stance ?? "") || "Not provided";
    const status = getOptionLabel(PROFESSIONAL_STATUS_OPTIONS, me.profile.professional_status ?? "") || "Not provided";
    const profileStateItems = [
      { label: "Full name", value: me.profile.full_name || "Not provided" },
      { label: "Technical style", value: primaryStyle },
      { label: "Tactical style", value: tacticalStyle },
      { label: "Stance", value: stance },
      { label: "Status", value: status },
      { label: "Record", value: me.profile.record || "Not provided" },
      { label: "Draft step", value: draft ? `${nextStepNumber} / 6` : "Not started" },
    ];

    return (
      <>
        <section className="hero-panel">
          <div className="hero-header">
            <div className="hero-panel-copy">
              <p className="eyebrow">Overview</p>
              <h1 className="hero-title">Control the full camp from one athlete workspace.</h1>
              <p>Resume onboarding, generate a plan, and reopen past camps in one place.</p>
            </div>
            <div className="status-card">
              <p className="status-label">Next action</p>
              <h2 className="plan-summary-title">{latestPlan ? "Open current plan" : "Finish onboarding"}</h2>
              <p className="muted">
                {latestPlan
                  ? `Latest plan created ${new Date(latestPlan.created_at).toLocaleString()}.`
                  : `Draft is parked on step ${nextStepNumber} of 6.`}
              </p>
              <div className="plan-summary-actions">
                <Link href={latestPlan ? `/plans/${latestPlan.plan_id}` : "/onboarding"} className="cta">
                  {latestPlan ? "Open latest plan" : "Resume onboarding"}
                </Link>
                <Link href="/plans" className="ghost-button">
                  View history
                </Link>
              </div>
            </div>
          </div>

          <div className="metric-grid">
            <article className="metric-card">
              <p className="kicker">Saved plans</p>
              <p className="metric-value">{plans.length}</p>
              <p className="muted">All generations stay in history.</p>
            </article>
            <article className="metric-card">
              <p className="kicker">Primary style</p>
              <p className="metric-value">{primaryStyle}</p>
              <p className="muted">Pulled from your athlete profile.</p>
            </article>
            <article className="metric-card">
              <p className="kicker">Fight date</p>
              <p className="metric-value">{latestIntake?.fight_date || latestPlan?.fight_date || "Not provided"}</p>
              <p className="muted">Using your latest saved intake.</p>
            </article>
          </div>
        </section>

        <section className="overview-grid">
          <article className="list-card overview-card">
            <div className="overview-card-header">
              <p className="kicker">Onboarding</p>
              <h2>Current profile state</h2>
            </div>
            <div className="overview-card-body">
              <OverviewDetailGrid items={profileStateItems} />
              <div className="plan-card-actions">
                <Link href="/onboarding" className="secondary-button">
                  {draft ? "Resume onboarding" : "Start onboarding"}
                </Link>
                <Link href="/settings" className="ghost-button">
                  Update settings
                </Link>
              </div>
            </div>
          </article>

          <article className="list-card overview-card">
            <div className="overview-card-header">
              <p className="kicker">History</p>
              <h2>Recent plans</h2>
            </div>
            <div className="overview-card-body">
              {plans.length ? (
                <div className="plan-history-list">
                  {plans.slice(0, 2).map((plan) => (
                    <article key={plan.plan_id} className="plan-history-row">
                      <div className="plan-history-copy">
                        <p className="label">Fight date</p>
                        <h3 className="plan-card-title">{getPlanDisplayName(plan)}</h3>
                        <p className="muted">Created {new Date(plan.created_at).toLocaleString()}</p>
                      </div>
                      <div className="plan-history-meta">
                        <span className="badge">{plan.status}</span>
                        <Link href={`/plans/${plan.plan_id}`} className="ghost-button">
                          Open plan
                        </Link>
                      </div>
                    </article>
                  ))}
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
