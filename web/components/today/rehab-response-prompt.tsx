"use client";

import { useState } from "react";

import { submitRehabResponses } from "@/lib/api";
import type {
  RehabDuringResponse,
  RehabLimitResponse,
  RehabResponsePrompt as RehabResponsePromptModel,
} from "@/lib/types";

const DURING_LABELS: Record<RehabDuringResponse, string> = {
  better: "Better",
  same: "Same",
  worse: "Worse",
  not_sure: "Not sure",
};

const LIMIT_LABELS: Record<RehabLimitResponse, string> = {
  no: "No",
  reduced: "Reduced it",
  stopped: "Stopped",
};

type Answer = {
  during?: RehabDuringResponse;
  limit?: RehabLimitResponse;
};

function ChoiceRow<Value extends string>({
  legend,
  legendId,
  options,
  labels,
  selected,
  disabled,
  onSelect,
}: Readonly<{
  legend: string;
  legendId: string;
  options: readonly Value[];
  labels: Record<Value, string>;
  selected: Value | undefined;
  disabled: boolean;
  onSelect: (value: Value | undefined) => void;
}>) {
  return (
    <div className="session-feedback-question">
      <p className="session-feedback-legend" id={legendId}>
        {legend}
      </p>
      <div className="feedback-chips" role="group" aria-labelledby={legendId}>
        {options.map((value) => (
          <button
            key={value}
            type="button"
            className={selected === value ? "feedback-chip is-selected" : "feedback-chip"}
            aria-pressed={selected === value}
            disabled={disabled}
            onClick={() => onSelect(selected === value ? undefined : value)}
          >
            {labels[value] ?? value}
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * "How did the injury respond to the rehab work?" — asked once per injury,
 * right after a session that actually contained rehab for it.
 *
 * This is not the session review. That asks how the *session* was; this asks
 * how one *injury* behaved, and its answers become evidence attached to that
 * injury. The two stay separate on screen for the same reason they stay
 * separate in the data: programming feedback is not a clinical observation.
 *
 * Every prompt here was raised by the server, which had already established
 * that identifiable rehab targeted a known injury. The athlete is asked what
 * they observed and nothing else — no mechanism, no diagnosis, no
 * interpretation, and no pain score invented out of a better/same/worse answer.
 * Skipping is a real option: an unanswered injury records nothing at all, which
 * is truthful, where a default "same" would be a report the athlete never made.
 */
export function RehabResponsePrompt({
  token,
  planId,
  sessionId,
  trainingDay,
  prompts,
  onDismiss,
}: Readonly<{
  token: string;
  planId: string;
  sessionId: string;
  /** Sent only for a retro-logged session; omitted means "the one just finished". */
  trainingDay?: string;
  prompts: RehabResponsePromptModel[];
  onDismiss: () => void;
}>) {
  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSent, setIsSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Only fully answered injuries are sent. A half-answered one is not a partial
  // observation to store, it is an unfinished question.
  const complete = prompts
    .map((prompt) => ({ prompt, answer: answers[prompt.injury_id] }))
    .filter(
      (entry): entry is { prompt: RehabResponsePromptModel; answer: Required<Answer> } =>
        Boolean(entry.answer?.during && entry.answer?.limit),
    );

  async function submit() {
    if (isSubmitting || complete.length === 0) {
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      await submitRehabResponses(token, {
        plan_id: planId,
        session_id: sessionId,
        training_day: trainingDay ?? null,
        answers: complete.map(({ prompt, answer }) => ({
          injury_id: prompt.injury_id,
          injury_episode_id: prompt.injury_episode_id,
          during_response: answer.during,
          limit_response: answer.limit,
        })),
      });
      setIsSent(true);
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "That could not be saved. Try again.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  if (prompts.length === 0) {
    return null;
  }

  if (isSent) {
    return (
      <section className="feedback-card rehab-response-card" aria-label="Injury response">
        <p className="feedback-question" role="status">
          Logged against your injury. Thank you.
        </p>
      </section>
    );
  }

  return (
    <section className="feedback-card rehab-response-card" aria-label="Injury response">
      <p className="session-feedback-title">How did the rehab work go?</p>
      <p className="muted session-feedback-intro">
        Answer for the injury you did the work for. This is kept with that injury, separately
        from your session review.
      </p>

      {prompts.map((prompt) => {
        const answer = answers[prompt.injury_id] ?? {};
        return (
          <div key={prompt.injury_id} className="rehab-response-injury">
            <p className="rehab-response-injury-label">{prompt.injury_label}</p>
            <ChoiceRow
              legend={prompt.during_question}
              legendId={`rehab-during-${prompt.injury_id}`}
              options={prompt.during_options}
              labels={DURING_LABELS}
              selected={answer.during}
              disabled={isSubmitting}
              onSelect={(value) =>
                setAnswers((current) => ({
                  ...current,
                  [prompt.injury_id]: { ...current[prompt.injury_id], during: value },
                }))
              }
            />
            <ChoiceRow
              legend={prompt.limit_question}
              legendId={`rehab-limit-${prompt.injury_id}`}
              options={prompt.limit_options}
              labels={LIMIT_LABELS}
              selected={answer.limit}
              disabled={isSubmitting}
              onSelect={(value) =>
                setAnswers((current) => ({
                  ...current,
                  [prompt.injury_id]: { ...current[prompt.injury_id], limit: value },
                }))
              }
            />
          </div>
        );
      })}

      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="feedback-actions">
        <button
          type="button"
          className="primary-button"
          disabled={isSubmitting || complete.length === 0}
          onClick={submit}
        >
          {isSubmitting ? "Saving…" : "Save"}
        </button>
        <button type="button" className="ghost-button" disabled={isSubmitting} onClick={onDismiss}>
          Skip
        </button>
      </div>
    </section>
  );
}
