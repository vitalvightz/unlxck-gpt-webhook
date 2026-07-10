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
 */
export function TodayDecisionPanel({
  banner,
  tier,
}: {
  banner: TodayDecisionBanner | null;
  tier?: TodayDecisionTier;
}) {
  if (!banner) {
    return null;
  }
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
      </div>
    </div>
  );
}
