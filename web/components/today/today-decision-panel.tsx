"use client";

import {
  getDecisionTier,
  getTierMeta,
  type TodayDecisionBanner,
  type TodayDecisionTier,
} from "@/lib/today";
import type { TodayCommandView } from "@/lib/types";

type TodayDecisionConfidence = NonNullable<
  TodayCommandView["today"]["recommendation_confidence"]
>;

const CONFIDENCE_LABELS: Record<TodayDecisionConfidence, string> = {
  high: "High",
  moderate: "Moderate",
  low: "Low",
};

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
 *   CONTEXT     what influenced that?  -> the camp around the decision
 *   CONFIDENCE  how sure is Unlxck?    -> how much this rested on
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
 * `confidence` is how much the call had to go on, which the engine knows for
 * certain. It is not confidence that the call is RIGHT, which would need outcome
 * data the product does not collect yet. At high it lists what was available; at
 * anything less it names what was missing, which is the more useful half.
 */
export function TodayDecisionPanel({
  banner,
  tier,
  triggers,
  context,
  sources,
  confidence,
  confidenceNote,
}: {
  banner: TodayDecisionBanner | null;
  tier?: TodayDecisionTier;
  triggers?: string[];
  context?: string[];
  sources?: string[];
  confidence?: TodayDecisionConfidence | null;
  confidenceNote?: string;
}) {
  if (!banner) {
    return null;
  }
  const triggerLabels = clean(triggers);
  const contextLabels = clean(context);
  const usedSources = clean(sources);
  const note = (confidenceNote ?? "").trim();
  // The backend sends a band only when it has trigger codes to judge the
  // decision by. Rendering a default would put a confident "High" on a
  // recommendation stored before the engine recorded triggers, which is the one
  // decision nothing is known about.
  const band = confidence ?? null;
  const hasEvidence = triggerLabels.length > 0 || contextLabels.length > 0 || band !== null;
  // Headline the tier ("Stop today" etc.) so Today matches the Overview action
  // framing; the chip carries the tier marker and the detail keeps the specifics.
  // Prefer the authoritative backend tier when supplied so the headline can never
  // disagree with the resolved decision.
  const tierLabel = getTierMeta(tier ?? getDecisionTier(banner)).label;
  return (
    <div
      className="today-decision-banner"
      data-state={banner.displayState}
      data-tone={banner.tone}
      role="status"
    >
      <span className="today-decision-icon" aria-hidden="true">
        {banner.chip}
      </span>
      <div className="today-decision-body">
        <p className="today-decision-title">{tierLabel}</p>
        {banner.action ? <p className="today-decision-action">{banner.action}</p> : null}
        <p className="today-decision-detail">{banner.detail}</p>
        {banner.safety ? <p className="today-decision-safety">{banner.safety}</p> : null}
        {hasEvidence ? (
          <dl className="today-decision-evidence">
            {triggerLabels.length ? (
              <div className="today-decision-row">
                <dt>Trigger</dt>
                <dd>{triggerLabels.join(" · ")}</dd>
              </div>
            ) : null}
            {contextLabels.length ? (
              <div className="today-decision-row">
                <dt>Context</dt>
                <dd>{contextLabels.join(" · ")}</dd>
              </div>
            ) : null}
            {band ? (
              <div className="today-decision-row" data-band={band}>
                <dt>Confidence</dt>
                <dd>
                  <span className="today-decision-band">{CONFIDENCE_LABELS[band]}</span>
                  {band === "high" && usedSources.length ? (
                    <ul className="today-decision-inputs">
                      {usedSources.map((source) => (
                        <li key={source}>{source}</li>
                      ))}
                    </ul>
                  ) : null}
                  {band !== "high" && note ? (
                    <span className="today-decision-gap">{note}</span>
                  ) : null}
                </dd>
              </div>
            ) : null}
          </dl>
        ) : null}
      </div>
    </div>
  );
}

function clean(values: string[] | undefined): string[] {
  return (values ?? []).filter((value) => value.trim());
}
