"use client";

import Image from "next/image";
import { useEffect, useId, useRef, useState } from "react";

import { submitSessionFeedback } from "@/lib/api";
import {
  SESSION_DIFFICULTY_OPTIONS,
  SESSION_FEEDBACK_INTRO,
  SESSION_FEEDBACK_PROMPT,
  SESSION_FEEDBACK_TITLE,
  SESSION_INSTRUCTIONS_OPTIONS,
  SESSION_PLAN_ACCURACY_OPTIONS,
  hasSessionFeedbackContent,
} from "@/lib/session-feedback";
import type { SessionFeedbackAnswers } from "@/lib/types";

type ChoiceRowProps<Value extends string> = {
  legend: string;
  options: ReadonlyArray<readonly [label: string, value: Value]>;
  selected: Value | undefined;
  onSelect: (value: Value | undefined) => void;
  disabled: boolean;
};

/** One question: a label and its mutually exclusive chips. Tapping the selected
 *  chip clears it, so a mis-tap does not lock in an answer the athlete never
 *  meant to give. */
function ChoiceRow<Value extends string>({
  legend,
  options,
  selected,
  onSelect,
  disabled,
}: ChoiceRowProps<Value>) {
  return (
    <div className="session-feedback-question">
      <p className="session-feedback-legend" id={`session-feedback-${legend.toLowerCase().replace(/\s+/g, "-")}`}>
        {legend}
      </p>
      <div
        className="feedback-chips"
        role="group"
        aria-labelledby={`session-feedback-${legend.toLowerCase().replace(/\s+/g, "-")}`}
      >
        {options.map(([label, value]) => (
          <button
            key={value}
            type="button"
            className={selected === value ? "feedback-chip is-selected" : "feedback-chip"}
            aria-pressed={selected === value}
            disabled={disabled}
            onClick={() => onSelect(selected === value ? undefined : value)}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * The review offered right after a session is logged as done or modified.
 *
 * Two stages on purpose. The first is a single question with two buttons, so
 * finishing a session never costs the athlete a form; only a tester who opts in
 * sees the three quick questions, and the comment box and screenshot stay
 * behind a disclosure below those. Forcing the long form on every completion is
 * how you teach people to stop logging sessions.
 *
 * This is deliberately not the trial briefing. The briefing explains the
 * testing role once at sign-up; this collects one session's experience at the
 * moment it is freshest.
 */
export function SessionFeedbackPrompt({
  token,
  planId,
  sessionId,
  trainingDay,
  onDismiss,
}: Readonly<{
  token: string;
  planId: string;
  sessionId: string;
  /** Sent only for a retro-logged session; omitted means "the one just finished". */
  trainingDay?: string;
  onDismiss: () => void;
}>) {
  const fieldId = useId();
  const [isOpen, setIsOpen] = useState(false);
  const [answers, setAnswers] = useState<SessionFeedbackAnswers>({});
  const [comment, setComment] = useState("");
  const [showDetails, setShowDetails] = useState(false);
  const [screenshot, setScreenshot] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSent, setIsSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const submissionLockRef = useRef(false);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const canSubmit = hasSessionFeedbackContent(answers, comment, screenshot);

  function selectScreenshot(file: File | null) {
    setScreenshot(file);
    setPreviewUrl(file ? URL.createObjectURL(file) : null);
  }

  function removeScreenshot() {
    selectScreenshot(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function submit() {
    if (submissionLockRef.current || !canSubmit) {
      return;
    }
    submissionLockRef.current = true;
    setIsSubmitting(true);
    setError(null);
    try {
      await submitSessionFeedback(token, {
        plan_id: planId,
        session_id: sessionId,
        training_day: trainingDay,
        ...answers,
        comment,
        screenshot,
      });
      setIsSent(true);
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : "Feedback could not be sent. Try again.",
      );
    } finally {
      submissionLockRef.current = false;
      setIsSubmitting(false);
    }
  }

  if (isSent) {
    return (
      <section className="feedback-card session-feedback-card" aria-label="Session feedback">
        <p className="feedback-question" role="status">
          Feedback sent. Thank you.
        </p>
      </section>
    );
  }

  if (!isOpen) {
    return (
      <section className="feedback-card session-feedback-card" aria-label="Session feedback">
        <p className="feedback-question">{SESSION_FEEDBACK_PROMPT}</p>
        <div className="feedback-actions">
          <button type="button" className="secondary-button" onClick={() => setIsOpen(true)}>
            Give feedback
          </button>
          <button type="button" className="ghost-button" onClick={onDismiss}>
            Not now
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="feedback-card session-feedback-card" aria-label="Session feedback">
      <p className="session-feedback-title">{SESSION_FEEDBACK_TITLE}</p>
      <p className="muted session-feedback-intro">{SESSION_FEEDBACK_INTRO}</p>

      <ChoiceRow
        legend="Difficulty"
        options={SESSION_DIFFICULTY_OPTIONS}
        selected={answers.difficulty}
        onSelect={(value) => setAnswers((current) => ({ ...current, difficulty: value }))}
        disabled={isSubmitting}
      />
      <ChoiceRow
        legend="Instructions"
        options={SESSION_INSTRUCTIONS_OPTIONS}
        selected={answers.instructions}
        onSelect={(value) => setAnswers((current) => ({ ...current, instructions: value }))}
        disabled={isSubmitting}
      />
      <ChoiceRow
        legend="Plan accuracy"
        options={SESSION_PLAN_ACCURACY_OPTIONS}
        selected={answers.plan_accuracy}
        onSelect={(value) => setAnswers((current) => ({ ...current, plan_accuracy: value }))}
        disabled={isSubmitting}
      />

      {/* The text box and the screenshot sit behind a disclosure so the three
          taps above stay the whole ask for anyone who just wants to answer. */}
      {showDetails ? (
        <div className="session-feedback-details">
          <div className="field">
            <label htmlFor={`${fieldId}-comment`}>Comments (optional)</label>
            <textarea
              id={`${fieldId}-comment`}
              value={comment}
              maxLength={500}
              rows={3}
              onChange={(event) => setComment(event.target.value)}
            />
            <span className="muted feedback-counter">{comment.length}/500</span>
          </div>
          <div className="field">
            <label htmlFor={`${fieldId}-screenshot`}>Screenshot (optional)</label>
            <input
              ref={fileInputRef}
              id={`${fieldId}-screenshot`}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              onChange={(event) => selectScreenshot(event.target.files?.[0] ?? null)}
            />
            <p className="feedback-privacy-copy">
              Avoid uploading screenshots containing private messages, contact details, payment
              information, or unrelated health information.
            </p>
            {screenshot && previewUrl ? (
              <div className="feedback-attachment-preview">
                <Image
                  src={previewUrl}
                  alt="Selected screenshot preview"
                  width={640}
                  height={360}
                  unoptimized
                />
                <div className="feedback-attachment-meta">
                  <span>
                    <strong>{screenshot.name}</strong>
                  </span>
                  <button type="button" className="ghost-button" onClick={removeScreenshot}>
                    Remove image
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : (
        <button
          type="button"
          className="feedback-link session-feedback-disclosure"
          onClick={() => setShowDetails(true)}
        >
          Add a comment or screenshot
        </button>
      )}

      {error ? (
        <p className="feedback-error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="feedback-actions session-feedback-submit-row">
        <button
          type="button"
          className="cta"
          onClick={() => void submit()}
          disabled={isSubmitting || !canSubmit}
        >
          {isSubmitting ? "Sending…" : "SUBMIT FEEDBACK"}
        </button>
        <button type="button" className="ghost-button" onClick={onDismiss} disabled={isSubmitting}>
          NOT NOW
        </button>
      </div>
    </section>
  );
}
