"use client";

import { type FormEvent, useId, useState } from "react";

import { useAppSession } from "@/components/auth-provider";
import { EffortSlider, FaceScale } from "@/components/rating-controls";
import { hasHealthDataConsent } from "@/lib/compliance";
import { sessionStatusLabel } from "@/lib/history";
import {
  completionRequiresModificationReason,
  completionRequiresReviewFields,
  getCompletionLabel,
  getCompletionReasonError,
  getCompletionReasonLabel,
} from "@/lib/today";
import type { TodayCompletionStatus } from "@/lib/types";
import { useTranslations as useAppTranslations } from "next-intl";


export type CompletionIntent = Extract<
  TodayCompletionStatus,
  "done" | "modified" | "skipped"
> | null;

export type CompletionFormPayload = {
  sessionRpe: number | null;
  painAfter: number | null;
  modificationReason: string;
  notes: string;
};

const PICKER_INTENTS: Exclude<CompletionIntent, null>[] = ["done", "modified", "skipped"];

/**
 * Shared done/modified/skipped logging form: RPE + pain-after for sessions that
 * were trained, and a required reason for modified and skipped sessions.
 *
 * Two modes:
 * - Today flow: the caller owns the intent (Mark done / Mark modified / Mark
 *   skipped buttons) and passes it in; the form renders nothing until set.
 * - Retro-log flow (`showStatusPicker`): a past session has no start/resume
 *   lifecycle, so the terminal status is picked inside the form instead.
 */
export function SessionCompletionForm({
  intent,
  isSubmitting,
  onCancel,
  onSubmit,
  showStatusPicker = false,
}: {
  intent: CompletionIntent;
  isSubmitting: boolean;
  onCancel: () => void;
  onSubmit: (status: Exclude<CompletionIntent, null>, payload: CompletionFormPayload) => Promise<void>;
  showStatusPicker?: boolean;
}) {
    const appText = useAppTranslations("AppText");
  const { me } = useAppSession();
  const canCollectPain = hasHealthDataConsent(me);
  const fieldId = useId();
  const [pickedIntent, setPickedIntent] = useState<CompletionIntent>(intent);
  const [sessionRpe, setSessionRpe] = useState<number | null>(null);
  const [painAfter, setPainAfter] = useState<number | null>(null);
  const [modificationReason, setModificationReason] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  const activeIntent = showStatusPicker ? pickedIntent : intent;

  if (!showStatusPicker && !intent) {
    return null;
  }

  const needsReviewFields = activeIntent ? completionRequiresReviewFields(activeIntent) : false;
  const needsReason = activeIntent ? completionRequiresModificationReason(activeIntent) : false;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!activeIntent) {
      setError("Choose how the session went first.");
      return;
    }
    if (needsReason && !modificationReason.trim()) {
      setError(getCompletionReasonError(activeIntent));
      return;
    }
    if (needsReviewFields && (sessionRpe === null || (canCollectPain && painAfter === null))) {
      setError(canCollectPain ? "Add session RPE and pain-after before saving." : "Add session RPE before saving.");
      return;
    }
    await onSubmit(activeIntent, {
      sessionRpe,
      painAfter,
      modificationReason: modificationReason.trim(),
      notes: notes.trim(),
    });
  }

  return (
    <form className="today-completion-form" onSubmit={handleSubmit}>
      {showStatusPicker ? (
        <div className="field">
          <span>{appText("text_01c8ee34ed69")}</span>
          <div className="today-action-row" role="group" aria-label={appText("text_1ffc39a64909")}>
            {PICKER_INTENTS.map((option) => (
              <button
                key={option}
                type="button"
                className={option === pickedIntent ? "secondary-button" : "ghost-button"}
                aria-pressed={option === pickedIntent}
                onClick={() => setPickedIntent(option)}
                disabled={isSubmitting}
              >
                {sessionStatusLabel(option)}
              </button>
            ))}
          </div>
        </div>
      ) : null}
      {needsReviewFields ? (
        <div className="today-completion-fields">
          <div className="field">
            <span>{appText("text_f3a719dc5cf3")}</span>
            <EffortSlider
              id={`${fieldId}-session-rpe`}
              ariaLabel={appText("text_f3a719dc5cf3")}
              value={sessionRpe}
              onChange={setSessionRpe}
            />
          </div>
          {canCollectPain ? <div className="field">
            <span>{appText("text_ff3440ed93c4")}</span>
            <FaceScale value={painAfter} onChange={setPainAfter} />
          </div> : null}
        </div>
      ) : null}
      {needsReason && activeIntent ? (
        <label className="field" htmlFor={`${fieldId}-reason`}>
          <span>{getCompletionReasonLabel(activeIntent)}</span>
          <textarea
            id={`${fieldId}-reason`}
            value={modificationReason}
            maxLength={2000}
            rows={2}
            onChange={(event) => setModificationReason(event.target.value)}
          />
        </label>
      ) : null}
      <label className="field" htmlFor={`${fieldId}-notes`}>
        <span>{appText("text_6239b93e96e9")}</span>
        <textarea
          id={`${fieldId}-notes`}
          value={notes}
          maxLength={2000}
          rows={2}
          onChange={(event) => setNotes(event.target.value)}
        />
      </label>
      {error ? <p className="today-inline-error" role="alert">{error}</p> : null}
      <div className="today-action-row">
        <button type="submit" className="cta" disabled={isSubmitting}>
          {isSubmitting
            ? appText("text_dc85af8f2b1d")
            : activeIntent
              ? `Save ${getCompletionLabel(activeIntent).toLowerCase()}`
              : appText("text_1509f561f241")}
        </button>
        <button type="button" className="ghost-button" onClick={onCancel} disabled={isSubmitting}>
          {appText("text_19766ed6ccb2")}</button>
      </div>
    </form>
  );
}
