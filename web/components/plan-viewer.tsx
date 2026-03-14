import Link from "next/link";

import { getOptionLabels, TECHNICAL_STYLE_OPTIONS } from "@/lib/intake-options";
import type { PlanDetail } from "@/lib/types";

function humanizeStatus(value: string) {
  return value.replace(/_/g, " ");
}

function formatStructuredValue(value: unknown, fallback: string) {
  if (value == null) {
    return fallback;
  }
  if (typeof value === "string") {
    return value.trim() || fallback;
  }
  if (typeof value === "object") {
    const entries = Array.isArray(value) ? value : Object.keys(value as Record<string, unknown>);
    if (!entries.length) {
      return fallback;
    }
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}

export function PlanViewer({ plan }: { plan: PlanDetail }) {
  const isAdmin = Boolean(plan.admin_outputs);
  const technicalStyles = getOptionLabels(TECHNICAL_STYLE_OPTIONS, plan.technical_style).join(", ") || "Unspecified";
  const athletePlanText = plan.outputs.plan_text.trim();
  const hasPublishedPlan = Boolean(athletePlanText);
  const statusLabel = humanizeStatus(plan.status || "generated");
  const stage2Status = humanizeStatus(plan.admin_outputs?.stage2_status || "legacy");

  return (
    <div className="page">
      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="kicker">Plan Detail</p>
            <h1>{plan.full_name}</h1>
            <p className="muted">
              {hasPublishedPlan
                ? "This is the validated athlete-facing plan now stored in the app."
                : "This plan is held back from the athlete view until Stage 2 clears review."}
            </p>
          </div>
          <div className="status-card">
            <p className="status-label">Status</p>
            <h2 className="plan-summary-title">{statusLabel}</h2>
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
                <p className="kicker">Stage 2</p>
                <h2 className="plan-summary-title">Automation status</h2>
              </div>
              <div className="plan-meta-grid">
                <article className="plan-meta-item">
                  <p className="plan-meta-label">Stage 2 status</p>
                  <p className="plan-meta-value">{stage2Status}</p>
                </article>
                <article className="plan-meta-item">
                  <p className="plan-meta-label">Attempts</p>
                  <p className="plan-meta-value">{plan.admin_outputs?.stage2_attempt_count || 0}</p>
                </article>
              </div>
            </section>
          ) : null}
        </aside>

        <section className="plan-text-panel">
          <div className="plan-header-row">
            <div>
              <p className="kicker">Athlete Plan</p>
              <h2>{hasPublishedPlan ? "Validated final plan" : "Pending finalization"}</h2>
            </div>
            <span className={`badge ${hasPublishedPlan ? "status-badge-success" : "status-badge-neutral"}`}>
              {hasPublishedPlan ? "Validated" : "Review required"}
            </span>
          </div>
          {hasPublishedPlan ? (
            <pre className="plan-text-block">{athletePlanText}</pre>
          ) : (
            <div className="support-panel">
              <div className="form-section-header">
                <p className="kicker">Publishing hold</p>
                <h3>Plan not yet released</h3>
              </div>
              <p className="muted">
                The automation flow generated a plan that still needs manual review before it can be shown to the athlete.
              </p>
            </div>
          )}
        </section>
      </div>

      {isAdmin ? (
        <div className="admin-output-grid">
          <section className="viewer-panel">
            <div className="form-section-header">
              <p className="kicker">Stage 1</p>
              <h3>Draft plan</h3>
            </div>
            <pre className="code-block">{plan.admin_outputs?.draft_plan_text || "No Stage 1 draft."}</pre>
          </section>
          <section className="viewer-panel">
            <div className="form-section-header">
              <p className="kicker">Stage 2</p>
              <h3>Latest model output</h3>
            </div>
            <pre className="code-block">{plan.admin_outputs?.final_plan_text || "No Stage 2 output."}</pre>
          </section>
          <section className="viewer-panel">
            <div className="form-section-header">
              <p className="kicker">Internal Notes</p>
              <h3>Coach/internal output</h3>
            </div>
            <pre className="code-block">{plan.admin_outputs?.coach_notes || "No internal notes."}</pre>
          </section>
          <section className="viewer-panel">
            <div className="form-section-header">
              <p className="kicker">Validator</p>
              <h3>Latest review report</h3>
            </div>
            <pre className="code-block">
              {formatStructuredValue(plan.admin_outputs?.stage2_validator_report, "No validator report.")}
            </pre>
          </section>
          <section className="viewer-panel">
            <div className="form-section-header">
              <p className="kicker">Stage 2 Brief</p>
              <h3>Planning brief</h3>
            </div>
            <pre className="code-block">
              {formatStructuredValue(plan.admin_outputs?.planning_brief, "No planning brief.")}
            </pre>
          </section>
          <section className="viewer-panel">
            <div className="form-section-header">
              <p className="kicker">Handoff</p>
              <h3>Automation prompt</h3>
            </div>
            <pre className="code-block">{plan.admin_outputs?.stage2_handoff_text || "No handoff text."}</pre>
          </section>
          <section className="viewer-panel">
            <div className="form-section-header">
              <p className="kicker">Retry</p>
              <h3>Repair prompt</h3>
            </div>
            <pre className="code-block">{plan.admin_outputs?.stage2_retry_text || "No retry prompt."}</pre>
          </section>
          <section className="viewer-panel">
            <div className="form-section-header">
              <p className="kicker">Payload</p>
              <h3>Stage 2 package</h3>
            </div>
            <pre className="code-block">
              {formatStructuredValue(plan.admin_outputs?.stage2_payload, "No Stage 2 payload.")}
            </pre>
          </section>
        </div>
      ) : null}
    </div>
  );
}
