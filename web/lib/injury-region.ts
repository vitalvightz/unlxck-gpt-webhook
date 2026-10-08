// Coarse body region for an injury's area text (a body-map label or a manually
// typed area). Used only to ORDER and FILTER the injury types offered, so the
// athlete sees the likely ones first — it never decides a type or a severity.

export type InjuryRegion = "head" | "hand_foot" | "tendon" | "joint" | "trunk" | "muscle" | "unknown";

const REGION_PATTERNS: Array<[InjuryRegion, RegExp]> = [
  ["head", /\b(head|neck|face|jaw|nose|eye|ear|skull|chin|cheek)\b/i],
  ["hand_foot", /\b(hands?|fingers?|thumbs?|knuckles?|feet|foot|toes?|heel)\b/i],
  ["tendon", /\b(achilles|tendon)\b/i],
  ["joint", /\b(shoulders?|elbows?|wrists?|hips?|knees?|ankles?)\b/i],
  ["trunk", /\b(ribs?|back|spine|lumbar)\b/i],
  ["muscle", /\b(biceps?|triceps?|forearms?|quads?|hamstrings?|calf|calves|glutes?|groin|traps?|chest|core|abs?|thighs?|shins?|arms?|legs?)\b/i],
];

export function getInjuryRegion(area: string): InjuryRegion {
  for (const [region, pattern] of REGION_PATTERNS) {
    if (pattern.test(area)) return region;
  }
  return "unknown";
}

/** Joints that hyperextend (straight-locking hinges and fingers). */
export function isHingeArea(area: string): boolean {
  return /\b(elbows?|knees?|wrists?|fingers?|thumbs?|hands?)\b/i.test(area);
}

/** Ball-and-socket joints where pinching (impingement) is a common complaint. */
export function isBallJointArea(area: string): boolean {
  return /\b(shoulders?|hips?)\b/i.test(area);
}

export function isRibArea(area: string): boolean {
  return /\bribs?\b/i.test(area);
}
