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

// Taxonomy family tokens. These are routing keys the planner classifies an
// injury BY, never words an athlete wrote or should read. Guided intake seeds a
// flag's description from its structured read of the injury, so the family token
// and its `family:specific` pair both end up stored alongside the real condition
// word ("blister. surface injury. surface injury:blister"). Display keeps the
// condition word and drops the plumbing around it.
const INTERNAL_TAXONOMY_SEGMENTS = new Set([
  "surface injury",
  "surface_injury",
  "non surface",
  "non_surface",
  "unspecified",
  "not sure",
  "not_sure",
]);

// The injury_type values guided intake stores (see the type options in
// components/guided-injury-card.tsx). Only these lead a `family:specific`
// taxonomy pair, so only these can make a colon mean "internal".
const TAXONOMY_FAMILIES = new Set([
  "surface_injury",
  "pain",
  "tightness",
  "sprain",
  "strain",
  "swelling",
  "instability",
  "unspecified",
  "fracture",
  "dislocation",
  "tendon_ligament",
  "post_surgery",
  "head_impact",
  "nerve_symptoms",
  "chest_breathing",
]);

// A `family:specific` taxonomy pair — "surface_injury:blister", and the
// underscore-stripped "surface injury:blister" the backend humanizes it into.
// Deliberately narrow: the whole segment must BE the pair, a recognised family
// on the left and a single bare token on the right. A colon is ordinary
// punctuation in athlete prose ("pain:sharp when running", "Left knee: sore"),
// and prose is what this is protecting.
const TAXONOMY_PAIR = /^([a-z][a-z_ ]*):([a-z0-9_]+)$/i;

function segmentIsInternal(segment: string): boolean {
  const normalized = segment.toLowerCase();
  if (INTERNAL_TAXONOMY_SEGMENTS.has(normalized)) {
    return true;
  }
  const pair = TAXONOMY_PAIR.exec(normalized);
  return pair !== null && TAXONOMY_FAMILIES.has(pair[1].replace(/\s+/g, "_"));
}

/**
 * The athlete-facing detail line for an injury: what the injury IS (and any
 * detail the athlete added), with the planner's internal taxonomy stripped out.
 *
 * Descriptions are stored as ". "-joined segments. A segment is dropped when it
 * is an internal taxonomy token, and the redundant "<body area>: " prefix is
 * removed so the line reads as the condition rather than restating the location
 * the label already shows.
 *
 * "Right shoulder: blister. surface injury. surface injury:blister" (body area
 * "Right shoulder") -> "blister"
 * "bruise. worse when sprinting" -> "bruise. worse when sprinting"
 */
export function formatInjuryDetail(
  description: string | null | undefined,
  options: { bodyArea?: string | null } = {},
): string {
  const raw = collapseWhitespace(String(description ?? ""));
  if (!raw) {
    return "";
  }
  const bodyKey = collapseWhitespace(String(options.bodyArea ?? "")).toLowerCase();
  const kept: string[] = [];
  const seen = new Set<string>();

  for (const rawSegment of raw.split(".")) {
    let segment = collapseWhitespace(rawSegment);
    if (!segment || segmentIsInternal(segment)) {
      continue;
    }
    // "Right shoulder: blister" -> "blister". The location is already the label.
    if (bodyKey && segment.toLowerCase().startsWith(`${bodyKey}:`)) {
      segment = collapseWhitespace(segment.slice(bodyKey.length + 1));
    }
    const key = segment.toLowerCase();
    if (!segment || key === bodyKey || seen.has(key)) {
      continue;
    }
    seen.add(key);
    kept.push(segment);
  }

  return kept.join(". ");
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
