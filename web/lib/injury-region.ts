// Coarse body region for an injury's area text (a body-map label or a manually
// typed area). Used only to ORDER and FILTER the injury types offered, so the
// athlete sees the likely ones first — it never decides a type or a severity.

export type InjuryRegion = "head" | "hand_foot" | "tendon" | "joint" | "trunk" | "muscle" | "unknown";

const REGION_PATTERNS: Array<[InjuryRegion, RegExp]> = [
  ["head", /\b(head|neck|face|jaw|tmj|nose|eye|eyebrows?|ears?|skull|chin|cheek|lips?|mouth|teeth|tooth|temple)\b/i],
  ["hand_foot", /\b(hands?|palms?|fingers?|fingertips?|pinky|thumbs?|knuckles?|feet|foot|toes?|toenails?|heels?|arch(es)?|plantar)\b/i],
  ["tendon", /\b(achilles|tendon|tendons)\b/i],
  ["joint", /\b(shoulders?|ac joint|elbows?|wrists?|hips?|knees?|kneecaps?|ankles?)\b/i],
  // "back of arm/thigh/knee..." names a limb, not the back.
  ["trunk", /\b(ribs?|back(?!\s+of\b)|spine|lumbar|ql|si joint|sacroiliac|sacrum|tailbone|coccyx|flanks?)\b/i],
  ["muscle", /\b(biceps?|triceps?|forearms?|quads?|quadriceps|hamstrings?|hamm(y|ies)|calf|calves|glutes?|piriformis|psoas|groin|adductors?|traps?|lats?|rhomboids?|delts?|deltoids?|pecs?|chest|core|abs?|obliques?|thighs?|shins?|arms?|legs?)\b/i],
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
