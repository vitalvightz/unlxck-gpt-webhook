// Central source of athlete-facing medical / injury / weight-cut safety copy.
//
// Rules for anything added here:
// - Keep wording direct and non-overpromising.
// - Unlxck is NOT medical advice and does NOT diagnose injuries or medically
//   clear an athlete. Never claim otherwise.
// - Prefer "training allowed by your current inputs" over "safe to train", and
//   "reduce or stop if symptoms worsen" over reassurance.
// - Coach / clinician advice always overrides the app.

export const SAFETY_NOT_MEDICAL_ADVICE =
  "Unlxck is not medical advice and does not diagnose injuries.";

export const SAFETY_COACH_OVERRIDE =
  "Advice from your coach or clinician always overrides the app.";

// One-line disclaimer for persistent / low-emphasis areas (footer, settings).
// Keep this longer version for wider screens.
export const SAFETY_DISCLAIMER_SHORT =
  "Unlxck is not medical advice and does not diagnose injuries or provide medical clearance. " +
  "Reduce or stop if symptoms worsen, seek medical help for red flags, and follow your coach or clinician.";

// Shorter disclaimer for mobile or otherwise tight layouts.
export const SAFETY_DISCLAIMER_TIGHT =
  "Unlxck is not medical advice. Stop if symptoms worsen, seek help for red flags, and follow your coach or clinician.";

// Red-flag symptoms that should prompt stopping and seeking help. Kept as a list
// so callers can render it compactly (expandable detail) without restating it.
export const SAFETY_RED_FLAGS: readonly string[] = [
  "Sharp pain, swelling, or joint instability",
  "Numbness, tingling, or weakness (neurological symptoms)",
  "Chest pain, faintness, or trouble breathing",
  "Severe dehydration",
  "Any symptom that gets worse instead of better",
];

export const SAFETY_RED_FLAG_HEADING = "Stop training and seek medical help for red flags";

export const SAFETY_RED_FLAG_ACTION =
  "If any of these appear, stop training and seek medical help.";

// Placed before / around injury intake.
export const INJURY_INTAKE_SAFETY =
  "Unlxck does not diagnose injuries or provide medical clearance. Use this to plan around what you " +
  "and your clinician already know. Stop training and seek medical help for sharp pain, swelling, " +
  "instability, neurological symptoms, chest pain, or faintness.";

// Today / daily check-in red-flag area.
export const TODAY_RED_FLAG_SAFETY =
  "These flags are not a diagnosis. If you have sharp pain, swelling, instability, neurological " +
  "symptoms, chest pain, or faintness, stop training and seek medical help.";

// Plan view active notes / red flags. Frames any "allowed" training as
// input-driven, never as medical clearance.
export const PLAN_SAFETY_NOTE =
  "Training shown here is allowed by your current inputs — it is not medical clearance. " +
  "Reduce or stop if symptoms worsen, and follow your coach or clinician.";

// Nutrition / weight-cut workspace.
export const WEIGHT_CUT_SAFETY =
  "Weight cuts and dehydration protocols carry real health risk and should be supervised by a " +
  "qualified professional. Unlxck is not medical advice. Stop and seek help for severe dehydration, " +
  "faintness, or chest pain.";
