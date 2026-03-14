"use client";

import Link from "next/link";

import { useAppSession } from "@/components/auth-provider";
import { getOptionLabel, TECHNICAL_STYLE_OPTIONS } from "@/lib/intake-options";

const demoMode = process.env.NEXT_PUBLIC_DEMO_MODE === "1";

function sortPlansByCreatedAt<T extends { created_at: string }>(plans: T[]): T[] {
  return [...plans].sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime());
}

export default function HomePage() {
  const { isReady, session, me } = useAppSession();

  if (!isReady) {
    return (
      <section className="panel loading-card">
        <p className="kicker">Overview</p>
        <h1>Loading your athlete workspace</h1>
        <p className="muted">Checking your saved onboarding and plan history now.</p>
      </section>
    );
  }

  if (session && me) {
    const plans = sortPlansByCreatedAt(me.plans);
    const latestPlan = plans[0] ?? null;
    const draft = (me.profile.onboarding_draft as { current_step?: number } | null) ?? null;
    const latestIntake = me.latest_intake;
    const nextStepNumber = Number.isFinite(Number(draft?.current_step ?? 0)) ? Number(draft?.current_step ?? 0) + 1 : 1;
    const primaryStyle = getOptionLabel(TECHNICAL_STYLE_OPTIONS, me.profile.technical_style[0] ?? "") || "Unspecified";

    return (
      <>
        <section className="hero-panel">
          <div className="hero-header">
            <div className="hero-panel-copy">
              <p className="eyebrow">Overview</p>
              <h1 className="hero-title">Control the full camp from one athlete workspace.</h1>
              <p>
                Resume onboarding, generate your next plan, and reopen past camps without leaving the product.
              </p>
            </div>
            <div className="status-card">
              <p className="status-label">Next action</p>
              <h2 className="plan-summary-title">{latestPlan ? "Open current plan" : "Finish onboarding"}</h2>
              <p className="muted">
                {latestPlan
                  ? `Latest plan created ${new Date(latestPlan.created_at).toLocaleString()}.`
                  : `Current draft is parked on step ${nextStepNumber} of 6.`}
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
              <p className="muted">Every generation stays available in your history.</p>
            </article>
            <article className="metric-card">
              <p className="kicker">Primary style</p>
              <p className="metric-value">{primaryStyle}</p>
              <p className="muted">Pulled directly from your athlete profile.</p>
            </article>
            <article className="metric-card">
              <p className="kicker">Fight date</p>
              <p className="metric-value">{latestIntake?.fight_date || latestPlan?.fight_date || "Not set"}</p>
              <p className="muted">Your latest saved intake drives the current camp context.</p>
            </article>
          </div>
        </section>

        <section className="overview-grid">
          <article className="list-card">
            <div className="form-section-header">
              <p className="kicker">Onboarding</p>
              <h2>Current profile state</h2>
            </div>
            <div className="meta-grid">
              <article className="plan-meta-item">
                <p className="plan-meta-label">Full name</p>
                <p className="plan-meta-value">{me.profile.full_name || "Unspecified"}</p>
              </article>
              <article className="plan-meta-item">
                <p className="plan-meta-label">Technical Style</p>
                <p className="plan-meta-value">{primaryStyle}</p>
              </article>
              <article className="plan-meta-item">
                <p className="plan-meta-label">Draft step</p>
                <p className="plan-meta-value">{draft ? `${nextStepNumber} / 6` : "Not started"}</p>
              </article>
            </div>
            <div className="plan-card-actions">
              <Link href="/onboarding" className="secondary-button">
                {draft ? "Resume onboarding" : "Start onboarding"}
              </Link>
              <Link href="/settings" className="ghost-button">
                Update settings
              </Link>
            </div>
          </article>

          <article className="list-card">
            <div className="form-section-header">
              <p className="kicker">History</p>
              <h2>Recent plans</h2>
            </div>
            {plans.length ? (
              <div className="plans-grid">
                {plans.slice(0, 2).map((plan) => (
                  <article key={plan.plan_id} className="plan-card">
                    <div className="plan-card-header">
                      <div>
                        <p className="label">Fight date</p>
                        <h3 className="plan-card-title">{plan.fight_date || "Open saved plan"}</h3>
                      </div>
                      <span className="badge">{plan.status}</span>
                    </div>
                    <p className="muted">Created {new Date(plan.created_at).toLocaleString()}</p>
                    <div className="plan-card-actions">
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
                <p className="muted">Finish onboarding to generate your first saved fight camp.</p>
                <div className="plan-card-actions">
                  <Link href="/onboarding" className="cta inline-cta">
                    Start onboarding
                  </Link>
                </div>
              </div>
            )}
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
          <p>
            UNLXCK now runs as a signed-in athlete product: onboarding, plan generation, plan history,
            and exports all in one place.
          </p>
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
        <article className="metric-card">
          <p className="kicker">Step 1</p>
          <h2>Sign up</h2>
          <p className="muted">Create an athlete account and keep your plan history in one place.</p>
        </article>
        <article className="metric-card">
          <p className="kicker">Step 2</p>
          <h2>Onboard</h2>
          <p className="muted">Fill out a structured intake instead of leaving the product for a form.</p>
        </article>
        <article className="metric-card">
          <p className="kicker">Step 3</p>
          <h2>Generate</h2>
          <p className="muted">Turn that intake into a saved fight camp plan with PDF access and history.</p>
        </article>
      </section>
    </>
  );
}
