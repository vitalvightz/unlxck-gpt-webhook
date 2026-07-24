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
//   * Other -> injects no condition word. The report then rests on the athlete's
//     own detail text (plus the body-map location), which the scorer escalates
//     only when the wording warrants it (e.g. "unstable", "gave way"). Absent such
//     wording there is simply no condition signal — "Other" is a catch-all for the
//     unusual, not an assertion that the injury is minor.
//
// A type is a REQUIRED explicit choice on the form (there is no default), so a
// report always carries a deliberate type intent rather than an accidental blank.
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

import { TODAY_INJURY_MAX_WORDS, TODAY_INJURY_TEXT_MAX } from "./input-limits.ts";

export type TodayInjuryType = "soreness" | "tightness" | "bruise" | "other";

/**
 * Clamp a daily-check-in injury text entry to the character and word caps
 * (`TODAY_INJURY_TEXT_MAX` / `TODAY_INJURY_MAX_WORDS`). Enforced as the athlete
 * types so a report stays a terse phrase, not a paragraph. A trailing space while
 * still under the word cap is preserved (so the next word can be started); once
 * the cap is exceeded the extra words are dropped.
 */
export function limitInjuryEntryText(value: string): string {
  const capped = value.slice(0, TODAY_INJURY_TEXT_MAX);
  const words = capped.split(/\s+/).filter(Boolean);
  if (words.length <= TODAY_INJURY_MAX_WORDS) {
    return capped;
  }
  return words.slice(0, TODAY_INJURY_MAX_WORDS).join(" ");
}

// Form-state type: "" is the unselected state, since a type must be chosen
// explicitly before the report can be added (no default selection).
export type TodayInjuryTypeSelection = TodayInjuryType | "";

export const NO_TODAY_INJURY_TYPE: TodayInjuryTypeSelection = "";

export const TODAY_INJURY_TYPE_OPTIONS: Array<{ value: TodayInjuryType; label: string }> = [
  { value: "soreness", label: "Soreness" },
  { value: "tightness", label: "Tightness" },
  { value: "bruise", label: "Bruise" },
  { value: "other", label: "Other" },
];

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
