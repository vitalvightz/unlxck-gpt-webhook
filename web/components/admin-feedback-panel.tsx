"use client";

import { useEffect, useState } from "react";

import { listAdminFeedback } from "@/lib/api";
import { formatAppDateTime } from "@/lib/date-format";
import type { AdminFeedbackRecord } from "@/lib/types";

const LABELS: Record<string, string> = {
  plan_usefulness: "Plan usefulness",
  recommendation_fit: "Recommendation fit",
  recommendation_safety: "Recommendation safety",
  bug_report: "Bug report",
  feature_request: "Feature request",
  safety_issue: "Safety issue",
  general_feedback: "General feedback",
};

function readable(value: string | null | undefined): string {
  return value ? value.replaceAll("_", " ") : "Not provided";
}

export function AdminFeedbackPanel({ token, reloadKey }: { token: string; reloadKey: number }) {
  const [feedback, setFeedback] = useState<AdminFeedbackRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    void listAdminFeedback(token)
      .then((rows) => {
        if (active) setFeedback(rows);
      })
      .catch((loadError: unknown) => {
        if (active) setError(loadError instanceof Error ? loadError.message : "Unable to load feedback.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token, reloadKey, retryKey]);

  return (
    <article className="list-card admin-feedback-panel">
      <div className="form-section-header">
        <div>
          <p className="kicker">Athlete voice</p>
          <h2>Latest feedback</h2>
          <p className="muted admin-panel-subtext">Safety reports are shown first. Email alerts are best-effort.</p>
        </div>
        <span className="badge">{loading ? "Checking" : `${feedback.length} recent`}</span>
      </div>

      {loading ? <p className="muted">Loading feedback...</p> : null}
      {!loading && error ? (
        <div className="support-panel">
          <p className="error-text">{error}</p>
          <button type="button" className="ghost-button" onClick={() => setRetryKey((value) => value + 1)}>
            Retry feedback
          </button>
        </div>
      ) : null}
      {!loading && !error && feedback.length === 0 ? (
        <div className="support-panel support-panel-success">
          <h3 className="form-section-title">No feedback yet.</h3>
          <p className="muted">Plan, recommendation, and global reports will appear here.</p>
        </div>
      ) : null}
      {!loading && !error && feedback.length > 0 ? (
        <div className="admin-feedback-list">
          {feedback.map((item) => (
            <article key={item.id} className="admin-feedback-row" data-priority={item.priority}>
              <div className="admin-feedback-heading">
                <div>
                  <p className="kicker">{LABELS[item.category] ?? readable(item.category)}</p>
                  <h3 className="plan-card-title">{item.submitter_name || "Authenticated user"}</h3>
                  <p className="muted">{item.submitter_email || item.submitted_by_profile_id}</p>
                </div>
                <span className="badge">{item.priority === "safety" ? "Safety" : readable(item.surface)}</span>
              </div>
              <div className="admin-feedback-meta">
                <span>Response: {readable(item.response)}</span>
                <span>Reason: {readable(item.reason)}</span>
                <span>Phase: {item.camp_phase || "Not set"}</span>
                <span>App: {item.app_version || "Unknown"}</span>
              </div>
              {item.comment ? <p className="admin-feedback-comment">{item.comment}</p> : null}
              <div className="admin-feedback-footer">
                <span>{formatAppDateTime(item.created_at)}</span>
                {item.contact_allowed ? <span>Contact permitted</span> : null}
                {item.has_screenshot ? <span>Private screenshot attached</span> : null}
              </div>
            </article>
          ))}
        </div>
      ) : null}
    </article>
  );
}
