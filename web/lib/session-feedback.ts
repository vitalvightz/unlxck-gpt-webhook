// The quick review offered after a completed session.
//
// Pure data + rules so the question set and the "is this worth sending"
// decision stay testable without a DOM, and so the prompt's copy lives in one
// place rather than being spelled out inline in JSX.

import type {
  SessionFeedbackAnswers,
  SessionFeedbackDifficulty,
  SessionFeedbackInstructions,
  SessionFeedbackPlanAccuracy,
  TodayCompletionStatus,
} from "@/lib/types";

export const SESSION_FEEDBACK_PROMPT = "How did this session feel?";
export const SESSION_FEEDBACK_TITLE = "HOW DID THAT SESSION GO?";
export const SESSION_FEEDBACK_INTRO =
  "Your feedback helps improve your future training and the UNLXCK private trial.";

export const SESSION_DIFFICULTY_OPTIONS: ReadonlyArray<
  readonly [label: string, value: SessionFeedbackDifficulty]
> = [
  ["Too easy", "too_easy"],
  ["Appropriate", "appropriate"],
  ["Too hard", "too_hard"],
];

export const SESSION_INSTRUCTIONS_OPTIONS: ReadonlyArray<
  readonly [label: string, value: SessionFeedbackInstructions]
> = [
  ["Clear", "clear"],
  ["Unclear", "unclear"],
];

export const SESSION_PLAN_ACCURACY_OPTIONS: ReadonlyArray<
  readonly [label: string, value: SessionFeedbackPlanAccuracy]
> = [
  ["Felt right", "felt_right"],
  ["Something was wrong", "something_wrong"],
];

/**
 * Only a session the athlete actually trained gets a review prompt.
 *
 * A skipped session was never experienced, so asking how it felt is noise; a
 * started-but-unfinished one has nothing to review yet. Both would train
 * testers to dismiss the prompt, which is the failure mode that matters — a
 * prompt people reflexively close collects nothing.
 */
export function shouldPromptSessionFeedback(status: TodayCompletionStatus | null): boolean {
  return status === "done" || status === "modified";
}

/**
 * A submission is worth sending once it carries at least one answer, a written
 * comment, or a screenshot. This mirrors the backend rule so an empty submit is
 * caught before the request rather than as a 422.
 */
export function hasSessionFeedbackContent(
  answers: SessionFeedbackAnswers,
  comment: string,
  screenshot: File | null,
): boolean {
  const hasAnswer = Boolean(answers.difficulty || answers.instructions || answers.plan_accuracy);
  return hasAnswer || comment.trim().length > 0 || screenshot !== null;
}
