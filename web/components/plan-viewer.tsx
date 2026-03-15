"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { getOptionLabels, TECHNICAL_STYLE_OPTIONS } from "@/lib/intake-options";
import { approvePlanForRelease, submitManualStage2 } from "@/lib/api";
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

function buildArtifactFilename(plan: PlanDetail, suffix: string) {
  const base = (plan.full_name || "athlete-plan")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "athlete-plan";
  return `${base}-${suffix}.txt`;
}

function downloadArtifact(text: string, filename: string) {
  if (!text.trim()) {
    return;
  }
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function ArtifactActions({
  artifactKey,
  text,
  filename,
}: {
  artifactKey: string;
  text: string;
  filename: string;
}) {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  useEffect(() => {
    if (!copiedKey) {
      return;
    }
    const timeout = window.setTimeout(() => setCopiedKey(null), 1800);
    return () => window.clearTimeout(timeout);
  }, [copiedKey]);

  if (!text.trim()) {
    return null;
  }

  async function handleCopy() {
    await navigator.clipboard.writeText(text);
    setCopiedKey(artifactKey);
  }

  return (
    <div className="plan-summary-actions">
      <button type="button" className="ghost-button" onClick={handleCopy}>
        {copiedKey === artifactKey ? "Copied" : "Copy text"}
      </button>
      <button type="button" className="ghost-button" onClick={() => downloadArtifact(text, filename)}>
        Download .txt
      </button>
    </div>
  );
}

function AdminArtifactSection({
  artifactKey,
  isOpen,
  onToggle,
  kicker,
  title,
  summary,
  description,
  text,
  filename,
}: {
  artifactKey: string;
  isOpen: boolean;
  onToggle: () => void;
  kicker: string;
  title: string;
  summary: string;
  description?: string;
  text: string;
  filename?: string;
}) {
  return (
    <section className={`accordion-item ${isOpen ? "accordion-item-open" : ""}`}>
      <button type="button" className="accordion-trigger" onClick={onToggle} aria-expanded={isOpen}>
        <div className="accordion-trigger-copy">
          <p className="kicker">{kicker}</p>
          <h3>{title}</h3>
          <p className="muted accordion-summary">{summary}</p>
        </div>
        <span className="accordion-chevron" aria-hidden="true">
          {isOpen ? "-" : "+"}
        </span>
      </button>
      {isOpen ? (
        <div className="accordion-panel">
          {description ? <p className="muted">{description}</p> : null}
          {filename ? <ArtifactActions artifactKey={artifactKey} text={text} filename={filename} /> : null}
          <pre className="code-block">{text}</pre>
        </div>
      ) : null}
    </section>
  );
}

export function PlanViewer({
  plan,
  accessToken,
  onPlanUpdated,
}: {
  plan: PlanDetail;
  accessToken: string | null;
  onPlanUpdated?: (plan: PlanDetail) => void;
}) {
  const isAdmin = Boolean(plan.admin_outputs);
  const technicalStyles = getOptionLabels(TECHNICAL_STYLE_OPTIONS, plan.technical_style).join(", ") || "Unspecified";
  const athletePlanText = plan.outputs.plan_text.trim();
  const hasPublishedPlan = Boolean(athletePlanText);
  const statusLabel = humanizeStatus(plan.status || "generated");
  const stage2Status = humanizeStatus(plan.admin_outputs?.stage2_status || "legacy");
  const handoffText = plan.admin_outputs?.stage2_handoff_text || "";
  const retryText = plan.admin_outputs?.stage2_retry_text || "";
  const draftText = plan.admin_outputs?.draft_plan_text || "No Stage 1 draft.";
  const latestStage2Text = plan.admin_outputs?.final_plan_text || "No Stage 2 output.";
  const coachNotesText = plan.admin_outputs?.coach_notes || "No internal notes.";
  const validatorText = formatStructuredValue(plan.admin_outputs?.stage2_validator_report, "No validator report.");
  const planningBriefText = formatStructuredValue(plan.admin_outputs?.planning_brief, "No planning brief.");
  const payloadText = formatStructuredValue(plan.admin_outputs?.stage2_payload, "No Stage 2 payload.");
  const approvableText =
    plan.admin_outputs?.final_plan_text?.trim() ||
    plan.admin_outputs?.draft_plan_text?.trim() ||
    athletePlanText ||
    "";
  const canApproveForRelease = isAdmin && !hasPublishedPlan && Boolean(approvableText);
  const approvalSourceLabel = plan.admin_outputs?.final_plan_text?.trim()
    ? "saved Stage 2 final output"
    : plan.admin_outputs?.draft_plan_text?.trim()
      ? "saved Stage 1 draft"
      : "current plan text";
  const [manualPlanText, setManualPlanText] = useState(plan.admin_outputs?.final_plan_text || "");
  const [manualSubmitPending, setManualSubmitPending] = useState(false);
  const [manualSubmitMessage, setManualSubmitMessage] = useState<string | null>(null);
  const [manualSubmitError, setManualSubmitError] = useState<string | null>(null);
  const [approvePending, setApprovePending] = useState(false);
  const [approveMessage, setApproveMessage] = useState<string | null>(null);
  const [approveError, setApproveError] = useState<string | null>(null);
  const [openAdminSection, setOpenAdminSection] = useState(() => {
    if (retryText.trim()) {
      return "retry";
    }
    if ((plan.admin_outputs?.final_plan_text || "").trim()) {
      return "final";
    }
    if (handoffText.trim()) {
      return "handoff";
    }
    return "draft";
  });

  useEffect(() => {
    setManualPlanText(plan.admin_outputs?.final_plan_text || "");
  }, [plan.plan_id, plan.admin_outputs?.final_plan_text]);

  useEffect(() => {
    setOpenAdminSection(
      retryText.trim()
        ? "retry"
        : (plan.admin_outputs?.final_plan_text || "").trim()
          ? "final"
          : handoffText.trim()
            ? "handoff"
            : "draft",
    );
  }, [plan.plan_id, handoffText, retryText, plan.admin_outputs?.final_plan_text]);

  async function handleManualStage2Submit() {
    if (!accessToken) {
      setManualSubmitError("Admin session missing. Please sign in again.");
      return;
    }
    if (!manualPlanText.trim()) {
      setManualSubmitError("Paste the GPT final plan before submitting.");
      return;
    }

    setManualSubmitPending(true);
    setManualSubmitError(null);
    setManualSubmitMessage(null);
    try {
      const updatedPlan = await submitManualStage2(accessToken, plan.plan_id, {
        final_plan_text: manualPlanText,
      });
      onPlanUpdated?.(updatedPlan);
      setManualSubmitMessage(
        updatedPlan.status === "ready"
          ? "Manual Stage 2 output passed validation and is now published in the app."
          : "Manual Stage 2 output was saved, but it still needs revision. The retry prompt below is updated.",
      );
    } catch (error) {
      setManualSubmitError(error instanceof Error ? error.message : "Unable to submit manual Stage 2 output.");
    } finally {
      setManualSubmitPending(false);
    }
  }

  async function handleApproveForRelease() {
    if (!accessToken) {
      setApproveError("Admin session missing. Please sign in again.");
      return;
    }
    if (!canApproveForRelease) {
      setApproveError("There is no saved draft or Stage 2 final text available to approve.");
      return;
    }

    setApprovePending(true);
    setApproveError(null);
    setApproveMessage(null);
    try {
      const updatedPlan = await approvePlanForRelease(accessToken, plan.plan_id);
      onPlanUpdated?.(updatedPlan);
      setApproveMessage("Plan approved and released to the athlete view.");
    } catch (error) {
      setApproveError(error instanceof Error ? error.message : "Unable to approve this plan for athlete view.");
    } finally {
      setApprovePending(false);
    }
  }

  const adminSections = [
    {
      artifactKey: "draft",
      kicker: "Stage 1",
      title: "Draft plan",
      summary: "Original planner output before the final Stage 2 rewrite.",
      text: draftText,
    },
    {
      artifactKey: "final",
      kicker: "Stage 2",
      title: "Latest model output",
      summary: "Most recent saved Stage 2 plan text.",
      text: latestStage2Text,
    },
    {
      artifactKey: "internal-notes",
      kicker: "Internal Notes",
      title: "Coach/internal output",
      summary: "Internal notes saved alongside the current plan.",
      text: coachNotesText,
    },
    {
      artifactKey: "validator",
      kicker: "Validator",
      title: "Latest review report",
      summary: "Structured validator report from the last Stage 2 review.",
      text: validatorText,
    },
    {
      artifactKey: "brief",
      kicker: "Stage 2 Brief",
      title: "Planning brief",
      summary: "Structured brief that Stage 2 used as its planning authority.",
      text: planningBriefText,
    },
    {
      artifactKey: "handoff",
      kicker: "Handoff",
      title: "Stage 2 handoff",
      summary: "Exact handoff prompt generated by the app for manual GPT runs.",
      description: "Use this if you want to run GPT-5.4 manually with the same Stage 2 handoff the app stored.",
      text: handoffText || "No handoff text.",
      filename: buildArtifactFilename(plan, "stage2-handoff"),
    },
    {
      artifactKey: "retry",
      kicker: "Retry",
      title: "Repair prompt",
      summary: "Exact retry prompt to use when the last Stage 2 attempt needs revision.",
      description: "Use this when the validator asked for one more manual repair pass.",
      text: retryText || "No retry prompt.",
      filename: buildArtifactFilename(plan, "stage2-retry"),
    },
    {
      artifactKey: "payload",
      kicker: "Payload",
      title: "Stage 2 package",
      summary: "Internal Stage 2 payload captured for audit and debugging.",
      text: payloadText,
    },
  ];

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
              {handoffText.trim() ? (
                <>
                  <p className="muted">
                    The exact Stage 2 handoff is already saved for this plan, so you can run a manual GPT-5.4 pass quickly if you want.
                  </p>
                  <ArtifactActions
                    artifactKey="stage2_handoff_text"
                    text={handoffText}
                    filename={buildArtifactFilename(plan, "stage2-handoff")}
                  />
                </>
              ) : null}
              {retryText.trim() ? (
                <>
                  <p className="muted">A repair prompt is also ready if you want to run the retry step manually.</p>
                  <ArtifactActions
                    artifactKey="stage2_retry_text"
                    text={retryText}
                    filename={buildArtifactFilename(plan, "stage2-retry")}
                  />
                </>
              ) : null}
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
              {canApproveForRelease ? (
                <>
                  <p className="muted">Current approval source: {approvalSourceLabel}. You can release it as-is, or replace it with a manual GPT pass below.</p>
                  <div className="plan-summary-actions">
                    <button type="button" className="cta" onClick={handleApproveForRelease} disabled={approvePending}>
                      {approvePending ? "Approving..." : "Approve for athlete view"}
                    </button>
                  </div>
                </>
              ) : null}
              {approveMessage ? <div className="success-banner">{approveMessage}</div> : null}
              {approveError ? <div className="error-banner">{approveError}</div> : null}
            </div>
          )}
        </section>
      </div>

      {isAdmin ? (
        <div className="admin-review-stack">
          <section className="viewer-panel">
            <div className="form-section-header">
              <p className="kicker">Admin Review</p>
              <h3>Manual Stage 2 actions</h3>
            </div>
            <p className="muted">
              Paste a manual GPT-5.4 final plan here. The app will validate it, publish it if it passes, or refresh the retry prompt if it still needs work.
            </p>
            {canApproveForRelease ? (
              <div className="support-panel">
                <div className="form-section-header">
                  <p className="kicker">Quick approval</p>
                  <h3>Release the current saved plan</h3>
                </div>
                <p className="muted">
                  If the current saved version is good enough, approve it directly for athlete view without rerunning Stage 2. Source: {approvalSourceLabel}.
                </p>
                <div className="plan-summary-actions">
                  <button type="button" className="cta" onClick={handleApproveForRelease} disabled={approvePending}>
                    {approvePending ? "Approving..." : "Approve for athlete view"}
                  </button>
                </div>
              </div>
            ) : null}
            {approveMessage ? <div className="success-banner">{approveMessage}</div> : null}
            {approveError ? <div className="error-banner">{approveError}</div> : null}
            <div className="field">
              <label htmlFor="manual-stage2-final-plan">Final plan text</label>
              <textarea
                id="manual-stage2-final-plan"
                rows={16}
                value={manualPlanText}
                onChange={(event) => setManualPlanText(event.target.value)}
                placeholder="Paste the manual Stage 2 final plan here"
              />
            </div>
            <div className="plan-summary-actions">
              <button type="button" className="cta" onClick={handleManualStage2Submit} disabled={manualSubmitPending}>
                {manualSubmitPending ? "Submitting..." : "Validate and save"}
              </button>
            </div>
            {manualSubmitMessage ? <div className="success-banner">{manualSubmitMessage}</div> : null}
            {manualSubmitError ? <div className="error-banner">{manualSubmitError}</div> : null}
          </section>
          <section className="viewer-panel">
            <div className="form-section-header">
              <p className="kicker">Stage 2 internals</p>
              <h3>Open one artifact at a time</h3>
            </div>
            <p className="muted">
              Internal notes, planning artifacts, and validator details now stay collapsed until you open the one you need.
            </p>
            <div className="accordion-list">
              {adminSections.map((section) => (
                <AdminArtifactSection
                  key={section.artifactKey}
                  artifactKey={section.artifactKey}
                  isOpen={openAdminSection === section.artifactKey}
                  onToggle={() =>
                    setOpenAdminSection((current) =>
                      current === section.artifactKey ? "" : section.artifactKey,
                    )
                  }
                  kicker={section.kicker}
                  title={section.title}
                  summary={section.summary}
                  description={section.description}
                  text={section.text}
                  filename={section.filename}
                />
              ))}
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
