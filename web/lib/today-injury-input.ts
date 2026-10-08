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
import { getInjuryRegion, isBallJointArea, isHingeArea, isRibArea } from "./injury-region.ts";

export type TodayInjuryType = "soreness" | "tightness" | "bruise" | "other";

/**
 * Clamp a daily-check-in injury text entry to the word and character caps
 * (`TODAY_INJURY_MAX_WORDS` / `TODAY_INJURY_TEXT_MAX`). Enforced as the athlete
 * types (and when a body-map label is inserted) so a report stays a terse phrase,
 * not a paragraph. A trailing space while still under the word cap is preserved
 * so the next word can be started; extra words past the cap are dropped. The
 * character cap trims at a WORD BOUNDARY so a word is never cut in half — unless a
 * single word is itself longer than the cap, where a hard cut is unavoidable.
 */
export function limitInjuryEntryText(value: string): string {
  const words = value.split(/\s+/).filter(Boolean);
  let limited =
    words.length > TODAY_INJURY_MAX_WORDS
      ? words.slice(0, TODAY_INJURY_MAX_WORDS).join(" ")
      : value;

  if (limited.length > TODAY_INJURY_TEXT_MAX) {
    const hardCut = limited.slice(0, TODAY_INJURY_TEXT_MAX);
    // Drop a half-cut trailing word only when there is an earlier word to keep;
    // a lone over-long word has no boundary, so the hard cut stands.
    limited = /\s/.test(hardCut) && /\S$/.test(hardCut)
      ? hardCut.replace(/\S+$/, "").replace(/\s+$/, "")
      : hardCut;
  }
  return limited;
}

/** True when clamping actually changed the entry — used to explain to the athlete
 * why a word/character was dropped, rather than removing it silently. */
export function isInjuryEntryLimited(value: string): boolean {
  return limitInjuryEntryText(value) !== value;
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

// "Other" opens these more specific types so the athlete can tap rather than type.
// Each one writes the SAME condition word an athlete would otherwise type into the
// note, and every word is one the shared injury scorer already recognises — so a
// tap is classified exactly like the typed word would be (serious ones such as a
// possible break or a head knock still escalate). Words the scorer ignores
// ("jammed", "clicking") or misreads ("cramp" -> strain) are deliberately absent.
export type TodayOtherInjuryType =
  | "sprain" | "strain" | "swelling" | "stiffness" | "instability" | "hyperextension"
  | "impingement" | "tendonitis" | "dislocation" | "fracture" | "concussion" | "nerve"
  | "cut" | "laceration" | "abrasion" | "blister";

export const TODAY_OTHER_INJURY_TYPES: Record<TodayOtherInjuryType, { label: string; word: string; serious?: boolean }> = {
  sprain: { label: "Sprain / rolled", word: "sprain" },
  strain: { label: "Strain / pulled", word: "strain" },
  swelling: { label: "Swelling", word: "swelling" },
  stiffness: { label: "Stiffness", word: "stiffness" },
  instability: { label: "Giving way", word: "instability" },
  hyperextension: { label: "Hyperextended", word: "hyperextension" },
  impingement: { label: "Pinching", word: "impingement" },
  tendonitis: { label: "Tendon pain", word: "tendonitis" },
  dislocation: { label: "Dislocated", word: "dislocation", serious: true },
  fracture: { label: "Possible break", word: "fracture", serious: true },
  concussion: { label: "Head knock / concussion", word: "concussion", serious: true },
  nerve: { label: "Numbness / tingling", word: "numbness and tingling", serious: true },
  cut: { label: "Cut", word: "cut" },
  laceration: { label: "Deep cut", word: "laceration" },
  abrasion: { label: "Graze / mat burn", word: "abrasion" },
  blister: { label: "Blister", word: "blister" },
};

const TODAY_SKIN_TYPES: TodayOtherInjuryType[] = ["cut", "laceration", "abrasion", "blister"];

/**
 * The "Other" types to offer for an area, most likely first. The area only orders
 * and filters the list; an unrecognised area gets every type.
 */
export function getTodayOtherInjuryTypes(area: string): { suggested: TodayOtherInjuryType[]; skin: TodayOtherInjuryType[] } {
  const region = getInjuryRegion(area);
  const suggested: TodayOtherInjuryType[] = (() => {
    switch (region) {
      case "head": return ["concussion", "swelling", "stiffness", "nerve"];
      case "hand_foot": return ["sprain", "swelling", ...(isHingeArea(area) ? ["hyperextension" as const] : []), "dislocation", "fracture", "nerve"];
      case "tendon": return ["tendonitis", "swelling", "stiffness", "strain"];
      case "joint": return ["sprain", "swelling", "instability", "stiffness",
        ...(isHingeArea(area) ? ["hyperextension" as const] : []), ...(isBallJointArea(area) ? ["impingement" as const] : []),
        "dislocation", "fracture"];
      case "trunk": return isRibArea(area) ? ["strain", "swelling", "fracture"] : ["strain", "stiffness", "nerve"];
      case "muscle": return ["strain", "swelling", "stiffness", "tendonitis"];
      default: return ["sprain", "strain", "swelling", "stiffness", "instability", "tendonitis", "dislocation", "fracture", "concussion", "nerve"];
    }
  })();
  // A blister is a hand/foot problem; elsewhere it only clutters the list.
  const skin = TODAY_SKIN_TYPES.filter((type) => type !== "blister" || region === "hand_foot" || region === "unknown");
  return { suggested, skin };
}

/** The "Other" type a saved description starts with, if any (for editing). */
export function readTodayOtherInjuryType(description: string): TodayOtherInjuryType | "" {
  const text = description.trim().toLowerCase();
  const match = (Object.entries(TODAY_OTHER_INJURY_TYPES) as Array<[TodayOtherInjuryType, { word: string }]>)
    .find(([, { word }]) => text === word || text.startsWith(`${word}.`));
  return match?.[0] ?? "";
}

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
  otherType?: TodayOtherInjuryType | "";
  detail: string;
}): string {
  const typeWord = input.injuryType === "other"
    ? (input.otherType ? TODAY_OTHER_INJURY_TYPES[input.otherType].word : "")
    : input.injuryType;
  const detail = collapseWhitespace(input.detail);
  return [typeWord, detail].filter(Boolean).join(". ");
}
