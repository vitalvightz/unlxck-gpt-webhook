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
const FILLER_WORDS = new Set([
  "is", "are", "was", "were", "been", "be",
  "has", "have", "had", "got", "getting", "gets",
  "feel", "feels", "feeling", "felt", "seem", "seems",
  "it", "this", "that", "a", "an", "the", "my", "some",
  "really", "quite", "very", "bit", "of", "in", "on", "with", "and",
]);

// Anatomical and clinical acronyms that keep their uppercase form. This is an
// explicit list rather than a general "all caps survives" rule, because shouty
// input ("LEFT SHOULDER IS BRUISED") would otherwise be preserved verbatim.
const CLINICAL_ACRONYMS = new Set([
  "ACL", "PCL", "MCL", "LCL", "UCL", "MPFL",
  "ATFL", "CFL", "PTFL", "TFCC", "SLAP",
  "IT", "ITB", "TFL", "SI", "AC", "SC",
  "MTSS", "DOMS", "ROM", "FAI", "GTPS", "CTS",
]);

// Spinal levels and level ranges: L5, C5, T4, L5-S1, C5-C6. A single letter
// followed by digits is never an English word, so this cannot swallow anatomy.
const SPINAL_LEVEL = /^[A-Za-z]\d+(?:-[A-Za-z]?\d+)*$/;

// Injury grades ("grade 2 tear") and any other bare figure the athlete typed.
const BARE_NUMBER = /^\d+$/;

function collapseWhitespace(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function capitalizeFirst(value: string): string {
  if (!value) {
    return value;
  }
  return value.charAt(0).toUpperCase() + value.slice(1);
}

// Resolve one location word to its display form, or null when it is filler that
// should be dropped entirely.
function resolveLocationWord(word: string): string | null {
  const upper = word.toUpperCase();
  const lower = word.toLowerCase();
  const isFiller = FILLER_WORDS.has(lower);

  // "IT" (iliotibial band) collides with the filler pronoun "it". Casing is the
  // only signal available: uppercase means the band, lowercase means the pronoun.
  if (CLINICAL_ACRONYMS.has(upper) && (!isFiller || word === upper)) {
    return upper;
  }
  if (isFiller) {
    return null;
  }
  if (SPINAL_LEVEL.test(word)) {
    return upper;
  }
  if (BARE_NUMBER.test(word)) {
    return word;
  }
  // Ordinary body words are lowercased so the label reads as one sentence
  // regardless of how the athlete or upstream parser capitalized the input.
  return lower;
}

// Build the location from the condition-stripped remainder: drop filler, keep
// clinical tokens verbatim, and collapse repeated words keeping the first
// occurrence. Parser debris can leave a body word duplicated ("left shoulder
// left" after stripping "(bruise, left)"), and a body location never
// legitimately repeats a word, so deduping is safe.
function buildLocation(remainder: string): string {
  const seen = new Set<string>();
  const words: string[] = [];

  // Strip punctuation debris but keep digits, slashes, and hyphens so grades and
  // spinal levels ("L5-S1", "grade 2") survive intact.
  for (const raw of collapseWhitespace(remainder.replace(/[^a-zA-Z0-9\s/-]/g, " ")).split(" ")) {
    if (!raw) {
      continue;
    }
    const word = resolveLocationWord(raw);
    if (word === null || seen.has(word.toLowerCase())) {
      continue;
    }
    seen.add(word.toLowerCase());
    words.push(word);
  }

  return words.join(" ");
}

/**
 * Normalize a raw injury description into a short athlete-facing label.
 *
 * "Left shoulder is bruised" -> "Left shoulder bruise"
 * "pulled right hamstring"   -> "Right hamstring strain"
 * "Left hamstring"           -> "Left hamstring" (no condition, returned as-is)
 * "ACL grade 2 tear"         -> "ACL grade 2 tear" (clinical detail preserved)
 * "L5-S1 stiffness"          -> "L5-S1 stiffness"
 */
export function normalizeInjuryLabel(raw: string | null | undefined): string {
  const trimmed = collapseWhitespace(String(raw ?? ""));
  if (!trimmed) {
    return "";
  }

  let condition: string | null = null;
  for (const [pattern, noun] of CONDITION_NOUNS) {
    if (pattern.test(trimmed)) {
      condition = noun;
      break;
    }
  }

  // No recognized condition: keep the original wording (only tidy the casing of
  // the first letter) so already-clean labels like "Left hamstring" pass through.
  if (!condition) {
    return capitalizeFirst(trimmed);
  }

  // Strip EVERY condition word from the remainder, not just the first match.
  // Parser strings often restate the condition ("contusion (bruise, left)"), so
  // removing only the matched token leaves debris like "...bruise left bruise".
  let remainder = trimmed;
  for (const [pattern] of CONDITION_NOUNS) {
    remainder = remainder.replace(new RegExp(pattern.source, "gi"), " ");
  }

  const location = buildLocation(remainder);

  return capitalizeFirst(location ? `${location} ${condition}` : condition);
}
