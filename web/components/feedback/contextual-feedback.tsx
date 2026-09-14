"use client";

import { useEffect, useRef, useState } from "react";

import {
  getPlanFeedback,
  getTodayFeedback,
  putPlanFeedback,
  putTodayFeedback,
} from "@/lib/api";
import type {
  ContextualFeedbackRequest,
  FeedbackRecord,
  FeedbackResponseValue,
} from "@/lib/types";
import { requestXpRefresh } from "@/lib/xp-events";
import { useTranslations as useAppTranslations } from "next-intl";


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

export function buildContextualFeedbackPayload(
  response: FeedbackResponseValue,
  selectedReason: string | null,
  comment: string,
): ContextualFeedbackRequest {
  return {
    response,
    reason: response === "no" ? selectedReason : null,
    comment: response === "yes" ? "" : comment,
  };
}

export const THUMB_PATHS = {
  up: "M7 10v10H3V10h4Zm2 0 3-7c2 0 3 1 3 3v2h4c1.2 0 2 .9 1.8 2l-1.4 8c-.2 1.1-1.2 2-2.4 2H9V10Z",
  down: "M7 14V4H3v10h4Zm2 0 3 7c2 0 3-1 3-3v-2h4c1.2 0 2-.9 1.8-2l-1.4-8c-.2-1.1-1.2-2-2.4-2H9v10Z",
} as const;

function ThumbIcon({ direction }: Readonly<{ direction: keyof typeof THUMB_PATHS }>) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
      <path d={THUMB_PATHS[direction]} fill="currentColor" />
    </svg>
  );
}

export function ContextualFeedback({
  token,
  surface,
  planId,
  className,
}: Readonly<{
  token: string;
  surface: "plan" | "daily_recommendation";
  planId?: string;
  className?: string;
}>) {
    const appText = useAppTranslations("AppText");
  const [record, setRecord] = useState<FeedbackRecord | null>(null);
  const [choice, setChoice] = useState<FeedbackResponseValue | null>(null);
  const [reason, setReason] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [editing, setEditing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const submissionInFlightRef = useRef(false);
  const userInteractedRef = useRef(false);
  const [submissionError, setSubmissionError] = useState<string | null>(null);

  const isPlan = surface === "plan";
  const reasons = isPlan ? PLAN_REASONS : DAILY_REASONS;

  useEffect(() => {
    let active = true;
    const request = isPlan && planId ? getPlanFeedback(token, planId) : getTodayFeedback(token);
    void request
      .then((saved) => {
        if (!active || !saved || userInteractedRef.current) return;
        setRecord(saved);
        setChoice(saved.response);
        setReason(saved.reason);
        setComment(saved.comment);
        setEditing(false);
      })
      .catch(() => {
        // Existing-response hydration is optional. Controls stay usable.
      });
    return () => {
      active = false;
    };
  }, [isPlan, planId, token]);

  async function save(response: FeedbackResponseValue, selectedReason = reason) {
    if (submissionInFlightRef.current) return;
    submissionInFlightRef.current = true;
    setSubmitting(true);
    setSubmissionError(null);
    const payload = buildContextualFeedbackPayload(response, selectedReason, comment);
    try {
      const saved = isPlan && planId
        ? await putPlanFeedback(token, planId, payload)
        : await putTodayFeedback(token, payload);
      // The feedback route awards XP before it returns. Refresh the shared XP
      // state immediately so the user sees that reward with the saved response.
      requestXpRefresh();
      setRecord(saved);
      setChoice(saved.response);
      setReason(saved.reason);
      setComment(saved.comment);
      setEditing(false);
    } catch (saveError) {
      setSubmissionError(saveError instanceof Error ? saveError.message : "Feedback could not be sent. Try again.");
    } finally {
      submissionInFlightRef.current = false;
      setSubmitting(false);
    }
  }

  function choose(nextChoice: FeedbackResponseValue) {
    userInteractedRef.current = true;
    setChoice(nextChoice);
    setReason(null);
    setEditing(true);
    setSubmissionError(null);
    if (nextChoice === "yes") void save("yes", null);
  }

  const showUnsafe = shouldShowUnsafeGuidance(choice, record?.response);

  return (
    <section
      className={className ? `feedback-card ${className}` : "feedback-card"}
      aria-label={isPlan ? appText("text_8f84b05cd4aa") : appText("text_cd728be7e17a")}
    >
      {record && !editing ? (
        <div className="feedback-sent-row" role="status">
          <span>{appText("text_5ac70032199b")}</span>
          <button
            type="button"
            className="feedback-link"
            onClick={() => {
              userInteractedRef.current = true;
              setEditing(true);
            }}
          >
            {appText("text_d5b60e7453a8")}</button>
        </div>
      ) : (
        <>
          <p className="feedback-question">
            {isPlan ? appText("text_27ec385cf8dc") : appText("text_73b6f67fb67a")}
          </p>
          <div className="feedback-actions" role="group" aria-label={appText("text_40850c327bac")}>
            <button
              type="button"
              className={choice === "yes" ? "feedback-choice is-selected" : "feedback-choice"}
              onClick={() => choose("yes")}
              disabled={submitting}
              aria-pressed={choice === "yes"}
            >
              <ThumbIcon direction="up" /> {appText("text_85a39ab345d6")}</button>
            <button
              type="button"
              className={choice === "no" ? "feedback-choice is-selected" : "feedback-choice"}
              onClick={() => choose("no")}
              disabled={submitting}
              aria-pressed={choice === "no"}
            >
              <ThumbIcon direction="down" /> {isPlan ? appText("text_4f4eb66adacf") : appText("text_1ea442a134b2")}
            </button>
            {!isPlan ? (
              <button
                type="button"
                className={choice === "unsafe" ? "feedback-choice feedback-unsafe is-selected" : "feedback-choice feedback-unsafe"}
                onClick={() => choose("unsafe")}
                disabled={submitting}
                aria-pressed={choice === "unsafe"}
              >
                {appText("text_8a03a7d2c33b")}</button>
            ) : null}
          </div>

          {choice === "no" ? (
            <div className="feedback-details">
              <div className="feedback-chips" role="group" aria-label={appText("text_956688a56605")}>
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
              <label htmlFor={`feedback-comment-${surface}`}>{appText("text_75a95c5e3872")}</label>
              <textarea
                id={`feedback-comment-${surface}`}
                value={comment}
                maxLength={500}
                rows={3}
                onChange={(event) => setComment(event.target.value)}
              />
              <div className="feedback-submit-row">
                <span className="muted">{comment.length}{appText("text_c17579733f80")}</span>
                <button type="button" className="cta" onClick={() => void save(choice)} disabled={submitting}>
                  {submitting ? appText("text_b8ed5279e897") : choice === "unsafe" ? appText("text_fe512d8ccbfa") : appText("text_8235980b80ad")}
                </button>
              </div>
            </div>
          ) : null}
        </>
      )}

      {showUnsafe ? <p className="feedback-unsafe-guidance" role="alert">{UNSAFE_GUIDANCE}</p> : null}
      {submissionError ? <p className="feedback-error" role="alert">{submissionError}</p> : null}
    </section>
  );
}
