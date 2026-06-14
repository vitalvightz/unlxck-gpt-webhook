import type { PlanAdvisory } from "@/lib/types";

// Sparring advisories are deterministic load-management flags. In practice most
// of them just restate load tweaks the engine already applies (deload/convert),
// which reads as redundant noise to the athlete. The one durable signal is
// injury risk, so the athlete view only surfaces an advisory that carries a
// MEANINGFUL injury-risk band. Everything else is suppressed.
//
// "green" (or absent) means no flagged injury risk — not shown.
const MEANINGFUL_RISK_BANDS: ReadonlyArray<NonNullable<PlanAdvisory["risk_band"]>> = [
  "amber",
  "red",
  "black",
];

// Severity order for picking the single most important advisory to surface.
const RISK_SEVERITY: Record<NonNullable<PlanAdvisory["risk_band"]>, number> = {
  green: 0,
  amber: 1,
  red: 2,
  black: 3,
};

/** Whether a risk band represents a real, surfaceable injury risk. */
export function isMeaningfulRiskBand(
  band: PlanAdvisory["risk_band"] | undefined,
): boolean {
  return band != null && MEANINGFUL_RISK_BANDS.includes(band);
}

/**
 * The single advisory worth showing the athlete: the most severe one that
 * carries a meaningful injury-risk band. Returns null when none qualify, so the
 * card is hidden rather than repeating load tweaks the plan already made.
 */
export function selectInjuryRiskAdvisory(
  advisories: PlanAdvisory[] | null | undefined,
): PlanAdvisory | null {
  if (!Array.isArray(advisories)) {
    return null;
  }
  const meaningful = advisories.filter((advisory) => isMeaningfulRiskBand(advisory?.risk_band));
  if (meaningful.length === 0) {
    return null;
  }
  return meaningful.reduce((best, current) =>
    RISK_SEVERITY[current.risk_band as NonNullable<PlanAdvisory["risk_band"]>] >
    RISK_SEVERITY[best.risk_band as NonNullable<PlanAdvisory["risk_band"]>]
      ? current
      : best,
  );
}
