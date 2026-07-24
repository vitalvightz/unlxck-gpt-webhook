// Today injury check-in: quick injury-type selection + optional detail.
//
// Today prioritises speed and consistency over perfect descriptions, so the add
// form captures location from the body map and the *feeling* from one tap rather
// than free-text medical wording. Only the low-stakes, unambiguous descriptors
// are offered as one-tap types:
//
//   * Soreness, Tightness, Bruise -> the injury scorer classifies each as a minor
//     (non-restricting) condition, so a single tap can never silently escalate a
//     report into a training restriction.
//   * Other -> injects no condition word; the optional detail line (or the body
//     map location alone) carries the report, so an unusual thing still reads
//     minor-by-default while escalating only if the athlete's own words warrant it.
//
// Deliberately absent: "Strain" is a diagnosis (the scorer treats it as a
// load-sensitive injury) and is inferred from area + severity, not tapped; "Sharp
// pain" and "Swelling" already have dedicated red-flag questions on the Today
// readiness check-in, so they are not duplicated here.
//
// The chosen type is composed into the declaration's ``description`` — the same
// text the shared injury scorer reads for both the display label
// (``build_injury_label``) and the safety consequence tier — so no new backend
// field is needed.

export type TodayInjuryType = "soreness" | "tightness" | "bruise" | "other";

export const TODAY_INJURY_TYPE_OPTIONS: Array<{ value: TodayInjuryType; label: string }> = [
  { value: "soreness", label: "Soreness" },
  { value: "tightness", label: "Tightness" },
  { value: "bruise", label: "Bruise" },
  { value: "other", label: "Other" },
];

export const DEFAULT_TODAY_INJURY_TYPE: TodayInjuryType = "other";

function collapseWhitespace(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

/**
 * Build the injury declaration ``description`` from the tapped type and the
 * optional one-line detail. "Other" contributes no condition word, so the result
 * is just the athlete's detail (or empty). The condition word leads so the scorer
 * reads it alongside the body-map location, e.g. body_area "left shoulder" +
 * description "soreness. tight after sprinting" -> "Left shoulder soreness".
 */
export function composeTodayInjuryDescription(input: {
  injuryType: TodayInjuryType;
  detail: string;
}): string {
  const typeWord = input.injuryType === "other" ? "" : input.injuryType;
  const detail = collapseWhitespace(input.detail);
  return [typeWord, detail].filter(Boolean).join(". ");
}
