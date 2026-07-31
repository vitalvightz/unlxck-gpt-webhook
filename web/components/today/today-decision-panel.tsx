"use client";

import { type TodayDecisionBanner, type TodayDecisionTier } from "@/lib/today";
import type { TodaySafetyCheck } from "@/lib/types";

/**
 * Compact train/modify/pull-back banner shown above today's blocks once the
 * athlete has checked in. Returns null before check-in. It frames the original
 * blocks — it never mutates the saved plan.
 *
 * The card answers the four questions an athlete actually has, in the order they
 * ask them:
 *
 *   DECISION    what should I do?      -> the tier headline and the action
 *   TRIGGER     why did it change?     -> what changed about the athlete
 *   CHECKED     what was assessed?     -> safety checks and their outcome
 *   CONTEXT     what influenced that?  -> the camp around the decision
 *   DECISION BASED ON                 -> which inputs were available
 *
 * Trigger and context are held apart because a flat list made "Fight week" a
 * peer of "High pain". Being in taper is a plan, not a symptom: it explains how
 * cautious the call is, and never that something is wrong. The backend does the
 * classification, so this panel only renders it.
 *
 * Triggers are contributors, never causes. The engine records which signals were
 * present when it decided; it does not establish that any one of them caused the
 * change, so the copy must not claim it did.
 *
 * The API keeps its confidence fields for compatibility. This panel describes
 * the evidence directly instead of translating data coverage into a confidence
 * claim the athlete could mistake for predictive certainty.
 */
export function TodayDecisionPanel({
  banner,
  tier,
  triggers,
  safetyChecks,
  context,
  sources,
  confidenceNote,
}: {
  banner: TodayDecisionBanner | null;
  tier?: TodayDecisionTier;
  triggers?: string[];
  /** Safety questions that were assessed, with their outcome — a stable skin
   * injury lands here rather than in the triggers, so "checked, no change"
   * never reads as "this reduced your session". Backend-classified. */
  safetyChecks?: TodaySafetyCheck[];
  context?: string[];
  sources?: string[];
  confidenceNote?: string;
}) {
  if (!banner) {
    return null;
  }
  const isPreview = tier === "preview" || banner.displayState === "preview";
  // Current-day readiness evidence cannot clear or restrict a future session.
  // Preview cards explain only which planned session their copy is framing.
  const triggerLabels = clean(isPreview ? undefined : triggers);
  const contextLabels = clean(isPreview ? undefined : context);
  const checks = (isPreview ? [] : (safetyChecks ?? [])).filter(
    (check) => check.label?.trim() && check.result_label?.trim(),
  );
  const usedSources = clean(isPreview ? ["next planned session"] : sources);
  const note = isPreview ? "" : (confidenceNote ?? "").trim();
  const hasEvidence =
    triggerLabels.length > 0 ||
    checks.length > 0 ||
    contextLabels.length > 0 ||
    usedSources.length > 0 ||
    Boolean(note);
  const evidenceCount =
    Number(triggerLabels.length > 0) +
    Number(checks.length > 0) +
    Number(contextLabels.length > 0) +
    Number(usedSources.length > 0 || Boolean(note));
  return (
    <div
      className="today-decision-banner"
      data-state={banner.displayState}
      data-tone={banner.tone}
      role="status"
    >
      <div className="today-decision-command">
        <div className="today-decision-heading">
          <span className="today-decision-icon" aria-hidden="true">
            {banner.chip}
          </span>
        </div>
        {banner.action ? <p className="today-decision-action">{banner.action}</p> : null}
        <p className="today-decision-detail">{banner.detail}</p>
        {banner.safety ? <p className="today-decision-safety">{banner.safety}</p> : null}
      </div>
      {hasEvidence ? (
        <dl className="today-decision-evidence" data-evidence-count={evidenceCount}>
          {triggerLabels.length ? (
            <div className="today-decision-row">
              <dt>Trigger</dt>
              <dd>
                <ul className="today-decision-values">
                  {triggerLabels.map((trigger) => (
                    <li key={trigger}>{trigger}</li>
                  ))}
                </ul>
              </dd>
            </div>
          ) : null}
          {checks.length ? (
            <div className="today-decision-row">
              <dt>Checked</dt>
              <dd>
                <ul className="today-decision-values">
                  {checks.map((check) => (
                    <li key={check.code}>{`${check.label} — ${check.result_label}`}</li>
                  ))}
                </ul>
              </dd>
            </div>
          ) : null}
          {contextLabels.length ? (
            <div className="today-decision-row">
              <dt>Context</dt>
              <dd>
                <ul className="today-decision-values">
                  {contextLabels.map((contextLabel) => (
                    <li key={contextLabel}>{contextLabel}</li>
                  ))}
                </ul>
              </dd>
            </div>
          ) : null}
          {usedSources.length || note ? (
            <div className="today-decision-row">
              <dt>Decision based on</dt>
              <dd>
                {usedSources.length ? (
                  <ul className="today-decision-inputs">
                    {usedSources.map((source) => (
                      <li key={source}>{source}</li>
                    ))}
                  </ul>
                ) : null}
                {note ? <span className="today-decision-gap">{note}</span> : null}
              </dd>
            </div>
          ) : null}
        </dl>
      ) : null}
    </div>
  );
}

function clean(values: string[] | undefined): string[] {
  return (values ?? []).filter((value) => value.trim());
}
