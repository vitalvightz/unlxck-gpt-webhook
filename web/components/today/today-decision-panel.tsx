"use client";

import {
  getDecisionTier,
  getTierMeta,
  type TodayDecisionBanner,
  type TodayDecisionTier,
} from "@/lib/today";

/**
 * Compact train/modify/pull-back banner shown above today's blocks once the
 * athlete has checked in. Returns null before check-in. It frames the original
 * blocks — it never mutates the saved plan.
 *
 * `contributors` and `sources` answer the athlete's two follow-up questions:
 * what moved today's call, and what it was read from. Both are computed by the
 * backend from the engine's own trigger codes, so this panel only renders them.
 *
 * They are worded as CONTRIBUTORS, never causes. The engine records which
 * signals were present when it decided; it does not establish that any one of
 * them caused the change, so the heading must not claim it did.
 */
export function TodayDecisionPanel({
  banner,
  tier,
  contributors,
  sources,
}: {
  banner: TodayDecisionBanner | null;
  tier?: TodayDecisionTier;
  contributors?: string[];
  sources?: string[];
}) {
  if (!banner) {
    return null;
  }
  const signals = (contributors ?? []).filter((value) => value.trim());
  const usedSources = (sources ?? []).filter((value) => value.trim());
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
        <p className="today-decision-detail">{banner.detail}</p>
        {banner.action ? <p className="today-decision-detail">{banner.action}</p> : null}
        {banner.safety ? <p className="today-decision-safety">{banner.safety}</p> : null}
        {signals.length ? (
          <div className="today-decision-signals">
            <p className="today-decision-signals-label" id="today-decision-signals-label">
              What moved this
            </p>
            <ul aria-labelledby="today-decision-signals-label">
              {signals.map((signal) => (
                <li key={signal}>{signal}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {usedSources.length ? (
          <p className="today-decision-sources">Based on {formatSourceList(usedSources)}.</p>
        ) : null}
      </div>
    </div>
  );
}

/** "a, b and c" — the plain spoken form, so the line reads like a coach rather
 * than a data export. */
function formatSourceList(sources: string[]): string {
  if (sources.length === 1) {
    return sources[0];
  }
  return `${sources.slice(0, -1).join(", ")} and ${sources[sources.length - 1]}`;
}
