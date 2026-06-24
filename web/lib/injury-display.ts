// Athlete-facing injury label normalization.
//
// Injuries are stored with whatever wording the athlete (or an upstream parser)
// produced — often a literal sentence like "Left shoulder is bruised". That is
// fine to keep internally, but the UI should show a short, normalized label:
// "Left shoulder bruise". This module maps the verbose internal description to a
// clean display label without losing the laterality or the body location.

// Verb/adjective phrasing for a condition -> the noun we show the athlete. Order
// matters: more specific conditions are listed before vaguer ones so, e.g., a
// "swollen sprain" surfaces as a sprain rather than swelling.
const CONDITION_NOUNS: Array<[RegExp, string]> = [
  [/\b(?:bruis(?:e|ed|ing)|contusion)\b/i, "bruise"],
  [/\b(?:hyperextend(?:ed|ing|s)?|hyperextension)\b/i, "hyperextension"],
  [/\b(?:disloc(?:ate|ated|ation))\b/i, "dislocation"],
  [/\b(?:fractur(?:e|ed)|broken|break)\b/i, "fracture"],
  [/\b(?:ruptur(?:e|ed)|tear|torn)\b/i, "tear"],
  [/\b(?:sprain(?:ed|ing)?)\b/i, "sprain"],
  [/\b(?:strain(?:ed|ing)?|pulled)\b/i, "strain"],
  [/\b(?:tendon[ai]tis|tendinopathy)\b/i, "tendonitis"],
  [/\b(?:imping(?:ed|ement))\b/i, "impingement"],
  [/\b(?:instability|unstable)\b/i, "instability"],
  [/\b(?:inflam(?:ed|mation|matory))\b/i, "inflammation"],
  [/\b(?:swollen|swelling)\b/i, "swelling"],
  [/\b(?:stiff(?:ness)?)\b/i, "stiffness"],
  [/\b(?:tight(?:ness)?)\b/i, "tightness"],
  [/\b(?:sore(?:ness)?|ach(?:e|es|ing|y))\b/i, "soreness"],
  [/\b(?:pain(?:ful)?|hurts?|hurting)\b/i, "pain"],
];

// Filler words that connect the location to the condition in natural phrasing
// ("shoulder is bruised", "my knee feels sore"). Removed so only the body
// location remains. Laterality (left/right) is deliberately NOT in this list.
const FILLER_WORDS =
  /\b(?:is|are|was|were|been|be|has|have|had|got|getting|gets|feels?|feeling|felt|seems?|it|this|that|a|an|the|my|some|really|quite|very|bit|of|in|on|with|and)\b/gi;

function collapseWhitespace(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function capitalizeFirst(value: string): string {
  if (!value) {
    return value;
  }
  return value.charAt(0).toUpperCase() + value.slice(1);
}

/**
 * Normalize a raw injury description into a short athlete-facing label.
 *
 * "Left shoulder is bruised" -> "Left shoulder bruise"
 * "pulled right hamstring"   -> "Right hamstring strain"
 * "Left hamstring"           -> "Left hamstring" (no condition, returned as-is)
 */
export function normalizeInjuryLabel(raw: string | null | undefined): string {
  const trimmed = collapseWhitespace(String(raw ?? ""));
  if (!trimmed) {
    return "";
  }

  let condition: string | null = null;
  let remainder = trimmed;
  for (const [pattern, noun] of CONDITION_NOUNS) {
    if (pattern.test(trimmed)) {
      condition = noun;
      remainder = trimmed.replace(pattern, " ");
      break;
    }
  }

  // No recognized condition: keep the original wording (only tidy the casing of
  // the first letter) so already-clean labels like "Left hamstring" pass through.
  if (!condition) {
    return capitalizeFirst(trimmed);
  }

  const location = collapseWhitespace(
    remainder.replace(FILLER_WORDS, " ").replace(/[^a-zA-Z\s/-]/g, " "),
  ).toLowerCase();

  return capitalizeFirst(location ? `${location} ${condition}` : condition);
}
