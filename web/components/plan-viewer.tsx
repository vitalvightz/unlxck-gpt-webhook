import Link from "next/link";

import { getOptionLabels, TECHNICAL_STYLE_OPTIONS } from "@/lib/intake-options";
import type { PlanDetail } from "@/lib/types";

export function PlanViewer({ plan }: { plan: PlanDetail }) {
  const isAdmin = Boolean(plan.admin_outputs);
  const technicalStyles = getOptionLabels(TECHNICAL_STYLE_OPTIONS, plan.technical_style).join(", ") || "Unspecified";

  return (
    <div className="page">
      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="kicker">Plan Detail</p>
            <h1>{plan.full_name}</h1>
            <p className="muted">Open the saved athlete-facing plan below. Presentation is improved here, but the raw output content is unchanged.</p>
          </div>
          <div className="status-card">
            <p className="status-label">Status</p>
            <h2 className="plan-summary-title">{plan.status}</h2>
            <p className="muted">Created {new Date(plan.created_at).toLocaleString()}</p>
          </div>
        </div>

        <div className="plan-summary-actions">
          <Link href="/plans" className="ghost-button">
            Back to plans
          </Link>
          {plan.outputs.pdf_url ? (
            <Link href={plan.outputs.pdf_url} target="_blank" rel="noreferrer" className="cta">
              Open PDF
            </Link>
          ) : null}
        </div>
      </section>

      <div className="plan-detail-layout">
        <aside className="plan-summary-stack">
          <section className="plan-summary-card">
            <div className="plan-summary-header">
              <p className="kicker">Summary</p>
              <h2 className="plan-summary-title">Camp context</h2>
            </div>
            <div className="plan-meta-grid">
              <article className="plan-meta-item">
                <p className="plan-meta-label">Fight date</p>
                <p className="plan-meta-value">{plan.fight_date || "Not set"}</p>
              </article>
              <article className="plan-meta-item">
                <p className="plan-meta-label">Technical Style</p>
                <p className="plan-meta-value">{technicalStyles}</p>
              </article>
              <article className="plan-meta-item">
                <p className="plan-meta-label">Created</p>
                <p className="plan-meta-value">{new Date(plan.created_at).toLocaleDateString()}</p>
              </article>
            </div>
          </section>

          {isAdmin ? (
            <section className="plan-summary-card">
              <div className="plan-summary-header">
                <p className="kicker">Internal</p>
                <h2 className="plan-summary-title">Admin-only context</h2>
              </div>
              <p className="muted">Coach notes and planning brief stay separate from the athlete-facing plan text below.</p>
            </section>
          ) : null}
        </aside>

        <section className="plan-text-panel">
          <div className="plan-header-row">
            <div>
              <p className="kicker">Athlete Plan</p>
              <h2>Your current camp</h2>
            </div>
            <span className="badge status-badge-neutral">Raw output</span>
          </div>
          <pre className="plan-text-block">{plan.outputs.plan_text}</pre>
        </section>
      </div>

      {isAdmin ? (
        <div className="admin-output-grid">
          <section className="viewer-panel">
            <div className="form-section-header">
              <p className="kicker">Internal Notes</p>
              <h3>Coach/internal output</h3>
            </div>
            <pre className="code-block">{plan.admin_outputs?.coach_notes || "No internal notes."}</pre>
          </section>
          <section className="viewer-panel">
            <div className="form-section-header">
              <p className="kicker">Stage 2 Brief</p>
              <h3>Planning brief</h3>
            </div>
            <pre className="code-block">{plan.admin_outputs?.planning_brief || "No planning brief."}</pre>
          </section>
        </div>
      ) : null}
    </div>
  );
}
