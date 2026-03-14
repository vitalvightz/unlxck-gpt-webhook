"use client";

import Link from "next/link";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { getOptionLabels, TECHNICAL_STYLE_OPTIONS } from "@/lib/intake-options";

export default function PlansPage() {
  const { me } = useAppSession();
  const plans = [...(me?.plans ?? [])].sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime());

  return (
    <RequireAuth>
      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="kicker">Plan History</p>
            <h1>Your saved plans</h1>
            <p className="muted">Open current and older plans from one saved history.</p>
          </div>
          <div className="status-card">
            <p className="status-label">Saved</p>
            <h2 className="plan-summary-title">{plans.length}</h2>
            <p className="muted">Every generated plan stays attached to your account.</p>
          </div>
        </div>

        <div className="plans-grid">
          {plans.map((plan) => (
            <article key={plan.plan_id} className="list-card plan-card">
              <div className="plan-card-header">
                <div>
                  <p className="label">Fight date</p>
                  <Link href={`/plans/${plan.plan_id}`}>
                    <h2 className="plan-card-title">{plan.fight_date || "Open plan"}</h2>
                  </Link>
                </div>
                <span className="badge">{plan.status}</span>
              </div>
              <p className="muted">{getOptionLabels(TECHNICAL_STYLE_OPTIONS, plan.technical_style).join(", ") || "Unspecified style"}</p>
              <p className="muted">Created {new Date(plan.created_at).toLocaleString()}</p>
              <div className="plan-card-actions">
                <Link href={`/plans/${plan.plan_id}`} className="ghost-button">
                  Open plan
                </Link>
                {plan.pdf_url ? (
                  <Link href={plan.pdf_url} target="_blank" rel="noreferrer" className="secondary-button">
                    Open PDF
                  </Link>
                ) : null}
              </div>
            </article>
          ))}

          {!plans.length ? (
            <article className="list-card plan-card">
              <div className="form-section-header">
                <p className="kicker">No plans yet</p>
                <h2>Start your first generation</h2>
              </div>
              <p className="muted">Complete onboarding to create the first saved fight camp in this workspace.</p>
              <div className="plan-card-actions">
                <Link href="/onboarding" className="cta inline-cta">
                  Start onboarding
                </Link>
              </div>
            </article>
          ) : null}
        </div>
      </section>
    </RequireAuth>
  );
}


