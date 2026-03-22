"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { getOptionLabels, TECHNICAL_STYLE_OPTIONS } from "@/lib/intake-options";
import { approvePlanForRelease, rejectApprovedPlan, submitManualStage2 } from "@/lib/api";
import type { PlanDetail } from "@/lib/types";

type ValidatorIssue = Record<string, unknown>;
type ReviewIssue = {
  code: string;
  title: string;
  message: string;
  severity: "error" | "warning";
  context?: string;
  snippet?: string;
};

const BLOCKING_WARNING_CODES = new Set([
  "missing_required_element",
  "phase_section_missing",
  "equipment_incongruent_selection",
  "unresolved_access_fallback",
  "missing_week_session_role",
  "late_camp_session_incomplete",
  "high_pressure_weight_cut_underaddressed",
]);

const ISSUE_TITLES: Record<string, string> = {
  restriction_violation: "Restriction violation",
  missing_required_element: "Missing phase-critical element",
  phase_section_missing: "Missing phase section",
  weak_anchor_session: "Weak anchor session",
  support_takeover_before_anchor: "Support work took over too early",
  conditional_conditioning_choice: "Conditioning is still unresolved",
  too_many_fallbacks: "Too many fallback branches",
  unresolved_access_fallback: "Fallback does not match real access needs",
  template_like_session_render: "Session still reads like a template",
  taper_option_overload: "Taper is too noisy",
  equipment_incongruent_selection: "Equipment mismatch",
  missing_week_session_role: "Week structure is missing a session",
  late_camp_session_incomplete: "Late-camp week is incomplete",
  weekly_session_overage: "Too many sessions in a week",
  weekly_rhythm_broken: "Weekly rhythm broke",
  missing_weight_cut_acknowledgement: "Weight-cut stress is missing",
  high_pressure_weight_cut_underaddressed: "High-pressure cut is underaddressed",
  sport_language_leak: "Cross-sport wording leaked in",
  overstyled_drill_name: "Naming still needs cleanup",
  gimmick_name: "Naming still needs cleanup",
};

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

function safeIssueList(value: unknown): ValidatorIssue[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is ValidatorIssue => Boolean(item) && typeof item === "object");
}

function issueTitle(code: string) {
  return ISSUE_TITLES[code] || humanizeStatus(code || "review issue");
}

function joinContextBits(bits: Array<string | null | undefined>) {
  return bits.filter((bit): bit is string => Boolean(bit && bit.trim())).join(" | ");
}

function normalizeIssueText(value: unknown) {
  return typeof value === "string" && value ? value.replace(/_/g, " ") : null;
}

function formatIssueContext(issue: ValidatorIssue) {
  const equipment =
    Array.isArray(issue.required_equipment) && issue.required_equipment.length
      ? `Needs ${issue.required_equipment.map((item) => String(item).replace(/_/g, " ")).join(", ")}`
      : null;

  return joinContextBits([
    typeof issue.phase === "string" && issue.phase ? issue.phase : null,
    typeof issue.week_index === "number" ? `Week ${issue.week_index}` : null,
    typeof issue.session_index === "number" ? `Session ${issue.session_index}` : null,
    normalizeIssueText(issue.requirement),
    normalizeIssueText(issue.restriction),
    equipment,
  ]);
}

function buildReviewIssue(issue: ValidatorIssue, severity: "error" | "warning"): ReviewIssue {
  const code = typeof issue.code === "string" ? issue.code : "review_issue";
  const message =
    typeof issue.message === "string" && issue.message.trim()
      ? issue.message.trim()
      : issueTitle(code);
  const snippet =
    typeof issue.line === "string" && issue.line.trim()
      ? issue.line.trim()
      : undefined;

  return {
    code,
    title: issueTitle(code),
    message,
    severity,
    context: formatIssueContext(issue) || undefined,
    snippet,
  };
}

function resolveWarningBuckets(report: Record<string, unknown> | null | undefined) {
  const warnings = safeIssueList(report?.warnings);
  const explicitBlockingWarnings = safeIssueList(report?.blocking_warnings);
  const explicitReviewFlags = safeIssueList(report?.review_flags);

  if (explicitBlockingWarnings.length || explicitReviewFlags.length) {
    return {
      blockingWarnings: explicitBlockingWarnings,
      reviewFlags: explicitReviewFlags,
    };
  }

  return {
    blockingWarnings: warnings.filter((issue) => BLOCKING_WARNING_CODES.has(String(issue.code || ""))),
    reviewFlags: warnings.filter((issue) => !BLOCKING_WARNING_CODES.has(String(issue.code || ""))),
  };
}

function pluralize(count: number, singular: string) {
  return `${count} ${singular}${count === 1 ? "" : "s"}`;
}

function buildReviewSummary(report: Record<string, unknown> | null | undefined, stage2Status: string) {
  const errors = safeIssueList(report?.errors).map((issue) => buildReviewIssue(issue, "error"));
  const { blockingWarnings, reviewFlags } = resolveWarningBuckets(report);
  const blocking = blockingWarnings.map((issue) => buildReviewIssue(issue, "warning"));
  const reviewFlagsMapped = reviewFlags.map((issue) => buildReviewIssue(issue, "warning"));
  const blockingCount =
    typeof report?.blocking_warning_count === "number" ? report.blocking_warning_count : blocking.length;
  const reviewFlagCount =
    typeof report?.review_flag_count === "number" ? report.review_flag_count : reviewFlagsMapped.length;
  const isPublishable =
    typeof report?.is_publishable === "boolean"
      ? report.is_publishable
      : errors.length === 0 && blocking.length === 0;
  const summary = {
    errors,
    blocking,
    reviewFlags: reviewFlagsMapped,
    blockingCount,
    reviewFlagCount,
    isPublishable,
  };

  if (errors.length + blocking.length + reviewFlagsMapped.length === 0) {
    return {
      ...summary,
      hasIssues: false,
      headline:
        stage2Status === "stage2_failed"
          ? "Stage 2 held this plan, but no detailed validator reasons were saved in the report."
          : "No validator issues were saved for this plan.",
      guidance:
        stage2Status === "stage2_failed"
          ? "Open the latest model output and retry prompt below to see what still needs work."
          : "This usually means the plan is held for workflow reasons rather than a specific validator issue.",
    };
  }

  const summaryParts = [
    errors.length ? pluralize(errors.length, "blocking error") : null,
    blocking.length ? pluralize(blocking.length, "blocking issue") : null,
    reviewFlagsMapped.length ? pluralize(reviewFlagsMapped.length, "review flag") : null,
  ].filter((part): part is string => Boolean(part));

  if (isPublishable) {
    const hasReviewFlags = reviewFlagsMapped.length > 0;
    return {
      ...summary,
      hasIssues: true,
      headline: hasReviewFlags
        ? `This plan is publishable. Only non-blocking review flags remain (${summaryParts.join(", ")}).`
        : "This plan is publishable and clear to release.",
      guidance: hasReviewFlags
        ? "You can release this plan now. The remaining flags are cleanup notes, not hold reasons."
        : "No blockers remain. Approval is now just a release decision.",
    };
  }

  return {
    ...summary,
    hasIssues: true,
    headline: `${summaryParts.join(" and ")} are keeping this Stage 2 plan in review.`,
    guidance:
      errors.length > 0
        ? "Fix the blocking issues first. Review flags are secondary until the blockers are gone."
        : "These blocking issues still need a retry or an explicit admin override before release.",
  };
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
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(artifactKey);
    } catch {
      // clipboard write failed; no visible feedback shown
    }
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

function QuickCopyButton({ text, artifactKey }: { text: string; artifactKey: string }) {
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
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(artifactKey);
    } catch {
      // clipboard write failed; no visible feedback shown
    }
  }

  return (
    <button type="button" className="ghost-button" onClick={handleCopy}>
      {copiedKey === artifactKey ? "Copied" : "Copy text"}
    </button>
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
  const technicalStyles = getOptionLabels(TECHNICAL_STYLE_OPTIONS, plan.technical_style).join(", ") || "Not provided";
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
  const validatorReport =
    plan.admin_outputs?.stage2_validator_report && typeof plan.admin_outputs.stage2_validator_report === "object"
      ? plan.admin_outputs.stage2_validator_report
      : {};
  const stage2ReviewSummary = buildReviewSummary(validatorReport, plan.admin_outputs?.stage2_status || "");
  const planningBriefText = formatStructuredValue(plan.admin_outputs?.planning_brief, "No planning brief.");
  const payloadText = formatStructuredValue(plan.admin_outputs?.stage2_payload, "No Stage 2 payload.");
  const reviewPlanText = (plan.admin_outputs?.final_plan_text || "").trim();
  const approvableText =
    plan.admin_outputs?.final_plan_text?.trim() ||
    plan.admin_outputs?.draft_plan_text?.trim() ||
    athletePlanText ||
    "";
  const canApproveForRelease = isAdmin && !hasPublishedPlan && Boolean(approvableText);
  const canRejectApproval = isAdmin && hasPublishedPlan;
  const approveButtonLabel = stage2ReviewSummary.isPublishable ? "Approve for athlete view" : "Approve anyway";
  const reviewPanelClassName = `support-panel stage2-review-panel ${stage2ReviewSummary.isPublishable ? "" : "support-panel-alert"}`.trim();
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
  const [rejectPending, setRejectPending] = useState(false);
  const [rejectMessage, setRejectMessage] = useState<string | null>(null);
  const [rejectError, setRejectError] = useState<string | null>(null);
  const [stage2RetryInProgress, setStage2RetryInProgress] = useState(false);
  const [stage2RetryJustCompleted, setStage2RetryJustCompleted] = useState<"passed" | "failed" | null>(null);
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
    setStage2RetryInProgress(true);
    setStage2RetryJustCompleted(null);
    setManualSubmitError(null);
    setManualSubmitMessage(null);
    try {
      const updatedPlan = await submitManualStage2(accessToken, plan.plan_id, {
        final_plan_text: manualPlanText,
      });
      const retryPassed = updatedPlan.status === "ready";
      setStage2RetryJustCompleted(retryPassed ? "passed" : "failed");
      onPlanUpdated?.(updatedPlan);
      setManualSubmitMessage(
        retryPassed
          ? "Manual Stage 2 output passed validation and is now published in the app."
          : "Manual Stage 2 output was saved, but it still needs revision. The retry prompt below is updated.",
      );
    } catch (error) {
      setStage2RetryJustCompleted(null);
      setManualSubmitError(error instanceof Error ? error.message : "Unable to submit manual Stage 2 output.");
    } finally {
      setManualSubmitPending(false);
      setStage2RetryInProgress(false);
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
    setRejectError(null);
    setRejectMessage(null);
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

  async function handleRejectApproval() {
    if (!accessToken) {
      setRejectError("Admin session missing. Please sign in again.");
      return;
    }
    if (!canRejectApproval) {
      setRejectError("Only released plans can be rejected back into review.");
      return;
    }

    setRejectPending(true);
    setRejectError(null);
    setRejectMessage(null);
    setApproveError(null);
    setApproveMessage(null);
    try {
      const updatedPlan = await rejectApprovedPlan(accessToken, plan.plan_id);
      onPlanUpdated?.(updatedPlan);
      setRejectMessage("Plan rejected and moved back to review so it can be approved again later.");
    } catch (error) {
      setRejectError(error instanceof Error ? error.message : "Unable to reject this released plan.");
    } finally {
      setRejectPending(false);
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
          {isAdmin && plan.athlete_id ? (
            <Link href={`/admin/athletes/${plan.athlete_id}`} className="ghost-button">
              View athlete profile
            </Link>
          ) : null}
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
                <p className="plan-meta-value">{plan.fight_date || "Not provided"}</p>
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
                <article className="plan-meta-item">
                  <p className="plan-meta-label">Release state</p>
                  <p className="plan-meta-value">
                    {stage2ReviewSummary.isPublishable ? "Publishable" : "Held"}
                  </p>
                </article>
                <article className="plan-meta-item">
                  <p className="plan-meta-label">Blocking issues</p>
                  <p className="plan-meta-value">{stage2ReviewSummary.errors.length + stage2ReviewSummary.blockingCount}</p>
                </article>
                <article className="plan-meta-item">
                  <p className="plan-meta-label">Review flags</p>
                  <p className="plan-meta-value">{stage2ReviewSummary.reviewFlagCount}</p>
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
            <>
              <div className="plan-summary-actions">
                <QuickCopyButton text={athletePlanText} artifactKey="athlete-plan" />
                {canRejectApproval ? (
                  <button type="button" className="ghost-button" onClick={handleRejectApproval} disabled={rejectPending}>
                    {rejectPending ? "Rejecting..." : "Reject approval"}
                  </button>
                ) : null}
              </div>
              <pre className="plan-text-block">{athletePlanText}</pre>
              {rejectMessage ? <div className="success-banner">{rejectMessage}</div> : null}
              {rejectError ? <div className="error-banner">{rejectError}</div> : null}
            </>
          ) : (
            <div className="plan-review-stack">
              {isAdmin ? (
                <>
                  {stage2RetryInProgress ? (
                    <section className="support-panel stage2-retry-banner stage2-retry-in-progress">
                      <div className="form-section-header">
                        <p className="kicker">Stage 2 Retry</p>
                        <h3>Retry in progress</h3>
                      </div>
                      <p className="muted">
                        Validating the submitted plan now. The validator results below are from the previous attempt and will be replaced when this retry completes.
                      </p>
                    </section>
                  ) : null}
                  {stage2RetryJustCompleted ? (
                    <section className={`support-panel stage2-retry-banner ${stage2RetryJustCompleted === "passed" ? "stage2-retry-passed" : "stage2-retry-failed"}`}>
                      <div className="form-section-header">
                        <p className="kicker">Stage 2 Retry — Attempt {plan.admin_outputs?.stage2_attempt_count || 1}</p>
                        <h3>{stage2RetryJustCompleted === "passed" ? "Retry passed — plan published" : "Retry completed — new validation results below"}</h3>
                      </div>
                      <p className="muted">
                        {stage2RetryJustCompleted === "passed"
                          ? "The submitted plan passed validation and has been published to the athlete view."
                          : "The submitted plan was validated. Blocking issues and review flags below reflect this latest attempt."}
                      </p>
                    </section>
                  ) : null}
                  <section className={`${reviewPanelClassName}${stage2RetryInProgress ? " stage2-review-panel-stale" : ""}`}>
                    <div className="form-section-header">
                      <p className="kicker">
                        Stage 2 review
                        {plan.admin_outputs?.stage2_attempt_count ? ` — attempt ${plan.admin_outputs.stage2_attempt_count}` : ""}
                        {stage2RetryInProgress ? " (previous attempt)" : ""}
                      </p>
                      <h3>{stage2ReviewSummary.isPublishable ? "Release decision" : "Why this plan is being held"}</h3>
                    </div>
                    <div className="stage2-review-state-row">
                      <span className={`badge ${stage2ReviewSummary.isPublishable ? "status-badge-success" : "issue-badge-error"}`}>
                        {stage2ReviewSummary.isPublishable ? "Publishable" : "Held"}
                      </span>
                      <span className="badge issue-badge-error">
                        {stage2ReviewSummary.errors.length + stage2ReviewSummary.blockingCount} blockers
                      </span>
                      <span className="badge issue-badge-warning">
                        {stage2ReviewSummary.reviewFlagCount} review flags
                      </span>
                    </div>
                    <p className="review-summary-text">{stage2ReviewSummary.headline}</p>
                    <p className="muted">{stage2ReviewSummary.guidance}</p>
                    {reviewPlanText ? (
                      <div className="plan-summary-actions">
                        <QuickCopyButton text={reviewPlanText} artifactKey="review-stage2" />
                      </div>
                    ) : null}
                    {stage2ReviewSummary.hasIssues ? (
                      <div className="review-issue-groups">
                        {stage2ReviewSummary.errors.length || stage2ReviewSummary.blocking.length ? (
                          <section className="review-issue-group">
                            <div className="review-issue-group-header">
                              <p className="review-issue-group-title">Blocking issues</p>
                              <span className="badge issue-badge-error">
                                {stage2ReviewSummary.errors.length + stage2ReviewSummary.blocking.length}
                              </span>
                            </div>
                            <div className="review-issue-list">
                              {stage2ReviewSummary.errors.map((issue, index) => (
                                <article key={`${issue.code}-${index}`} className="review-issue-item">
                                  <div className="review-issue-title-row">
                                    <p className="review-issue-title">{issue.title}</p>
                                    <span className="badge issue-badge-error">Error</span>
                                  </div>
                                  <p className="review-issue-message">{issue.message}</p>
                                  {issue.context ? <p className="review-issue-context">{issue.context}</p> : null}
                                  {issue.snippet ? <p className="review-issue-snippet">Line: {issue.snippet}</p> : null}
                                </article>
                              ))}
                              {stage2ReviewSummary.blocking.map((issue, index) => (
                                <article key={`${issue.code}-blocking-${index}`} className="review-issue-item">
                                  <div className="review-issue-title-row">
                                    <p className="review-issue-title">{issue.title}</p>
                                    <span className="badge issue-badge-error">Blocker</span>
                                  </div>
                                  <p className="review-issue-message">{issue.message}</p>
                                  {issue.context ? <p className="review-issue-context">{issue.context}</p> : null}
                                  {issue.snippet ? <p className="review-issue-snippet">Line: {issue.snippet}</p> : null}
                                </article>
                              ))}
                            </div>
                          </section>
                        ) : null}
                        {stage2ReviewSummary.reviewFlags.length ? (
                          <section className="review-issue-group">
                            <div className="review-issue-group-header">
                              <p className="review-issue-group-title">Review flags</p>
                              <span className="badge issue-badge-warning">{stage2ReviewSummary.reviewFlags.length}</span>
                            </div>
                            <div className="review-issue-list">
                              {stage2ReviewSummary.reviewFlags.map((issue, index) => (
                                <article key={`${issue.code}-${index}`} className="review-issue-item">
                                  <div className="review-issue-title-row">
                                    <p className="review-issue-title">{issue.title}</p>
                                    <span className="badge issue-badge-warning">Flag</span>
                                  </div>
                                  <p className="review-issue-message">{issue.message}</p>
                                  {issue.context ? <p className="review-issue-context">{issue.context}</p> : null}
                                  {issue.snippet ? <p className="review-issue-snippet">Line: {issue.snippet}</p> : null}
                                </article>
                              ))}
                            </div>
                          </section>
                        ) : null}
                      </div>
                    ) : null}
                  </section>
                </>
              ) : null}
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
                    <p className="muted">
                      Current approval source: {approvalSourceLabel}.{" "}
                      {stage2ReviewSummary.isPublishable
                        ? "Blocking validation is already clear, so approval is just a release decision."
                        : "This plan still has blocking issues, so approval here is an explicit override."}
                    </p>
                    <div className="plan-summary-actions">
                      <button
                        type="button"
                        className={stage2ReviewSummary.isPublishable ? "cta" : "ghost-button"}
                        onClick={handleApproveForRelease}
                        disabled={approvePending}
                      >
                        {approvePending ? "Approving..." : approveButtonLabel}
                      </button>
                    </div>
                  </>
                ) : null}
                {approveMessage ? <div className="success-banner">{approveMessage}</div> : null}
                {approveError ? <div className="error-banner">{approveError}</div> : null}
              </div>
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
                  <button
                    type="button"
                    className={stage2ReviewSummary.isPublishable ? "cta" : "ghost-button"}
                    onClick={handleApproveForRelease}
                    disabled={approvePending}
                  >
                    {approvePending ? "Approving..." : approveButtonLabel}
                  </button>
                </div>
              </div>
            ) : null}
            {approveMessage ? <div className="success-banner">{approveMessage}</div> : null}
            {approveError ? <div className="error-banner">{approveError}</div> : null}
            {rejectMessage ? <div className="success-banner">{rejectMessage}</div> : null}
            {rejectError ? <div className="error-banner">{rejectError}</div> : null}
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
