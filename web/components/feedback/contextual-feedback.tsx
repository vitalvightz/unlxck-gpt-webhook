"use client";

import { useEffect, useState } from "react";

import {
  getPlanFeedback,
  getTodayFeedback,
  putPlanFeedback,
  putTodayFeedback,
} from "@/lib/api";
import type { FeedbackRecord, FeedbackResponseValue } from "@/lib/types";

const PLAN_REASONS = [
  ["Too hard", "too_hard"],
  ["Too easy", "too_easy"],
  ["Does not fit my schedule", "schedule_mismatch"],
  ["Injury restrictions are wrong", "injury_restrictions_wrong"],
  ["Exercises are unsuitable", "exercises_unsuitable"],
  ["Instructions are unclear", "instructions_unclear"],
  ["Other", "other"],
] as const;

const DAILY_REASONS = [
  ["Too demanding", "too_demanding"],
  ["Too cautious", "too_cautious"],
  ["Ignored pain or injury", "pain_or_injury_ignored"],
  ["Does not match my training", "training_mismatch"],
  ["Repetitive", "repetitive"],
  ["Unclear", "unclear"],
] as const;

export const UNSAFE_GUIDANCE =
  "Do not continue this recommendation if it feels unsafe. Update your injury or readiness information and seek qualified medical help when necessary.";

export function shouldShowUnsafeGuidance(
  choice: FeedbackResponseValue | null,
  savedResponse: FeedbackResponseValue | null | undefined,
): boolean {
  return choice === "unsafe" || savedResponse === "unsafe";
}

function ThumbIcon({ down = false }: Readonly<{ down?: boolean }>) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
      <path
        d={down ? "M7 10v10H3V10h4Zm2 0 3-7c2 0 3 1 3 3v2h4c1.2 0 2 .9 1.8 2l-1.4 8c-.2 1.1-1.2 2-2.4 2H9V10Z" : "M7 14V4H3v10h4Zm2 0 3 7c2 0 3-1 3-3v-2h4c1.2 0 2-.9 1.8-2l-1.4-8c-.2-1.1-1.2-2-2.4-2H9v10Z"}
        fill="currentColor"
      />
    </svg>
  );
}

export function ContextualFeedback({
  token,
  surface,
  planId,
}: Readonly<{
  token: string;
  surface: "plan" | "daily_recommendation";
  planId?: string;
}>) {
  const [record, setRecord] = useState<FeedbackRecord | null>(null);
  const [choice, setChoice] = useState<FeedbackResponseValue | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isPlan = surface === "plan";
  const reasons = isPlan ? PLAN_REASONS : DAILY_REASONS;

  useEffect(() => {
    let active = true;
    setLoading(true);
    const request = isPlan && planId ? getPlanFeedback(token, planId) : getTodayFeedback(token);
    void request
      .then((saved) => {
        if (!active) return;
        setRecord(saved);
        setChoice(saved?.response ?? null);
        setReason(saved?.reason ?? null);
        setComment(saved?.comment ?? "");
      })
      .catch(() => {
        if (active) setError("Feedback is temporarily unavailable. Your plan is unaffected.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [isPlan, planId, token]);

  async function save(response: FeedbackResponseValue, selectedReason = reason) {
    if ((response === "no" || response === "unsafe") && submitting) return;
    setSubmitting(true);
    setError(null);
    const payload = {
      response,
      reason: response === "no" ? selectedReason : null,
      comment,
    };
    try {
      const saved = isPlan && planId
        ? await putPlanFeedback(token, planId, payload)
        : await putTodayFeedback(token, payload);
      setRecord(saved);
      setChoice(saved.response);
      setReason(saved.reason);
      setComment(saved.comment);
      setEditing(false);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Feedback could not be sent. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  function choose(nextChoice: FeedbackResponseValue) {
    setChoice(nextChoice);
    setReason(null);
    setEditing(true);
    setError(null);
    if (nextChoice === "yes") void save("yes", null);
  }

  const showUnsafe = shouldShowUnsafeGuidance(choice, record?.response);

  return (
    <section className="feedback-card" aria-label={isPlan ? "Plan feedback" : "Daily recommendation feedback"}>
      {record && !editing ? (
        <div className="feedback-sent-row" role="status">
          <span>Feedback sent</span>
          <button type="button" className="feedback-link" onClick={() => setEditing(true)}>
            Change response
          </button>
        </div>
      ) : (
        <>
          <p className="feedback-question">
            {isPlan ? "Is this plan useful?" : "Did this recommendation fit how you feel today?"}
          </p>
          {loading ? <p className="muted feedback-status" role="status">Loading feedback…</p> : null}
          {!loading ? (
            <div className="feedback-actions" role="group" aria-label="Choose a response">
              <button
                type="button"
                className={choice === "yes" ? "feedback-choice is-selected" : "feedback-choice"}
                onClick={() => choose("yes")}
                disabled={submitting}
                aria-pressed={choice === "yes"}
              >
                <ThumbIcon /> Yes
              </button>
              <button
                type="button"
                className={choice === "no" ? "feedback-choice is-selected" : "feedback-choice"}
                onClick={() => choose("no")}
                disabled={submitting}
                aria-pressed={choice === "no"}
              >
                <ThumbIcon down /> {isPlan ? "Needs improvement" : "No"}
              </button>
              {!isPlan ? (
                <button
                  type="button"
                  className={choice === "unsafe" ? "feedback-choice feedback-unsafe is-selected" : "feedback-choice feedback-unsafe"}
                  onClick={() => choose("unsafe")}
                  disabled={submitting}
                  aria-pressed={choice === "unsafe"}
                >
                  This recommendation may be unsafe
                </button>
              ) : null}
            </div>
          ) : null}

          {choice === "no" ? (
            <div className="feedback-details">
              <div className="feedback-chips" role="group" aria-label="Optional reason">
                {reasons.map(([label, code]) => (
                  <button
                    key={code}
                    type="button"
                    className={reason === code ? "feedback-chip is-selected" : "feedback-chip"}
                    aria-pressed={reason === code}
                    onClick={() => setReason(reason === code ? null : code)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {choice === "no" || choice === "unsafe" ? (
            <div className="feedback-comment">
              <label htmlFor={`feedback-comment-${surface}`}>Optional comment</label>
              <textarea
                id={`feedback-comment-${surface}`}
                value={comment}
                maxLength={500}
                rows={3}
                onChange={(event) => setComment(event.target.value)}
              />
              <div className="feedback-submit-row">
                <span className="muted">{comment.length}/500</span>
                <button type="button" className="cta" onClick={() => void save(choice)} disabled={submitting}>
                  {submitting ? "Sending…" : choice === "unsafe" ? "Send safety report" : "Send feedback"}
                </button>
              </div>
            </div>
          ) : null}
        </>
      )}

      {showUnsafe ? <p className="feedback-unsafe-guidance" role="alert">{UNSAFE_GUIDANCE}</p> : null}
      {error ? <p className="feedback-error" role="alert">{error}</p> : null}
    </section>
  );
}
