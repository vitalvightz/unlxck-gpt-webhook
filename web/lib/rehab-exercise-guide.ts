import type { StructuredBlock } from "./types";

/** A link to the existing prescribed exercise row, never a second player. */
export function rehabExerciseTarget(block: StructuredBlock): string | undefined {
  return block.block_type === "rehab" && block.rehab_drill_id && block.block_id
    ? `rehab-exercise-${block.block_id}` : undefined;
}

export const REHAB_RANGES: Record<string, string> = {
  floor_level: "Floor level only",
  comfortable_within_clinician_restrictions: "Comfortable range within clinician restrictions",
  comfortable_long_sitting_wall_press: "Seated with feet against the wall; no forced stretch",
};
const RESTRICTIONS: Record<string, string> = {
  seated_bilateral_floor_level_no_added_resistance: "Stay seated with both feet at floor level. No added resistance.",
  comfortable_range_within_clinician_restrictions: "Keep to a comfortable range within clinician restrictions.",
  no_standing_step_forced_range_or_automatic_increase: "No standing, step, forced range or automatic increase.",
  stop_for_worsening_during_or_delayed_symptoms: "Stop if symptoms worsen during or after the work.",
  no_sport_or_contact_clearance: "This exercise does not provide sport or contact clearance.",
  bodyweight_only_no_added_resistance: "Bodyweight only. No added resistance.",
  floor_only_no_step_or_below_floor_dorsiflexion: "Floor level only. No step or lowering below floor level.",
  follow_clinician_restrictions_no_training_or_contact_clearance: "Follow clinician restrictions. This exercise does not provide training or contact clearance.",
  no_speed_bouncing_hopping_or_automatic_progression: "No speed, bouncing, hopping or automatic progression.",
  stable_support_controlled_lowering: "Use stable support and controlled lowering.",
  stop_for_worsening_during_or_delayed_symptoms_seek_review: "Stop and seek review if symptoms worsen during or after the work.",
  stop_seek_assessment_for_snap_sudden_pain_or_loss_of_function: "Stop and seek assessment for a snap, sudden pain or loss of function.",
  wall_only_feet_near_wall_no_added_resistance: "Use a wall with feet near the wall. No added resistance.",
  elbows_below_shoulders_no_foot_distance_or_automatic_increase: "Keep elbows below shoulders. Do not move feet further away or automatically increase the exercise.",
  hand_weight_only_no_added_resistance: "Use the weight of your empty hand only. No added resistance.",
  supported_forearm_comfortable_range_within_clinician_restrictions: "Keep the forearm supported and use a comfortable range within clinician restrictions.",
  no_forceful_grip_speed_forced_range_or_automatic_increase: "No forceful grip, speed, forced range or automatic increase.",
};

export const rehabRestrictionText = (rule: string) => RESTRICTIONS[rule] ?? rule.replaceAll("_", " ");

/** Sentence boundaries only: no generated wording or dose parsed out of prose.
 * Decimal numbers and conditions within a sentence stay attached to the action.
 */
function sentences(value: string): string[] {
  return value.trim().split(/(?<=[.!?])\s+(?=[A-Z0-9])|\n+/u).map(s => s.trim()).filter(Boolean);
}
const safetySentence = /^(?:stop\b|seek\b|follow\b.*(?:clinician|restriction)|do not\b|don't\b|no\b|avoid\b|never\b|this\b.*(?:not|doesn't)|(?:use|stay|keep|work)\b.*(?:pain-free|low effort|comfortable effort|restrictions|;\s*(?:no|do not)))|\b(?:not a strength test|does not establish readiness)\b/i;
const textKey = (value: string) => value.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();

function safetyKey(rule: string): string {
  // Narrow equivalents only. Red flags, escalation, range, resistance, side,
  // timing and conditional restrictions outside these patterns stay verbatim.
  if (/^follow (?:your )?(?:existing )?clinician restrictions\.?$/i.test(rule)) return "clinician restrictions";
  if (/^stop if (?:pain or )?symptoms (?:increase|worsen) during or after (?:the )?(?:exercise|work|movement)\.?$/i.test(rule)) return "during or after symptom stop";
  return textKey(rule);
}

export function getRehabExerciseGuide(block: StructuredBlock) {
  const source = block.instructions?.trim()
    ? [block.instructions] : [block.execution_instructions ?? "", ...(block.coaching_cues ?? [])];
  const steps: string[] = [], safety: string[] = [];
  const stepKeys = new Set<string>(), safetyKeys = new Map<string, number>();
  function addSafety(rule: string) {
    const key = safetyKey(rule);
    const index = safetyKeys.get(key);
    if (index === undefined) { safetyKeys.set(key, safety.length); safety.push(rule); }
    // Keep the source version that explicitly names pain as well as symptoms.
    else if (key === "during or after symptom stop" && /pain or symptoms/i.test(rule)) safety[index] = rule;
  }
  for (const sentence of source.flatMap(sentences)) {
    if (safetySentence.test(sentence)) addSafety(sentence);
    else if (!stepKeys.has(textKey(sentence))) { stepKeys.add(textKey(sentence)); steps.push(sentence); }
  }
  for (const rule of [...(block.stop_rules ?? []), ...(block.mandatory_restrictions ?? [])]) {
    for (const sentence of sentences(rehabRestrictionText(rule))) addSafety(sentence);
  }
  const genericPainStop = safety.some(rule => /^stop if pain or symptoms (?:increase|worsen) during or after (?:the )?(?:exercise|work|movement)\.?$/i.test(rule));
  // A regional pain-only repeat adds no trigger to an explicit all-pain and
  // symptoms stop with the same during/after timing. Keep every other qualifier.
  const consolidatedSafety = genericPainStop ? safety.filter(rule =>
    !/^stop if (?!(?:not|no|or|and)\b)(?:[a-z]+ )?pain (?:increases|worsens) during or after (?:the )?(?:exercise|work|movement)\.?$/i.test(rule)) : safety;
  const metrics: { label: string; value: string }[] = [];
  const dose = block.dose;
  // An explicit empty approved dose remains self-paced, even if a legacy field
  // or bank metadata happens to carry a number. Never invent a starting dose.
  const sets = dose ? dose.sets : block.sets;
  const reps = dose ? dose.reps : block.reps;
  const duration = dose ? dose.duration_seconds : block.duration?.unit === "seconds" ? block.duration.value : null;
  const positive = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value) && value > 0;
  if (positive(duration)) metrics.push({ label: block.drill_snapshot?.contraction_type === "isometric" ? "Hold" : "Duration", value: `${duration}s` });
  if (positive(reps) || (typeof reps === "string" && reps.trim())) metrics.push({ label: "Reps", value: String(reps) });
  if (positive(sets)) metrics.push({ label: "Sets", value: String(sets) });
  const frequency = block.frequency ?? block.drill_snapshot?.prescription?.frequency;
  if (frequency === "daily") metrics.push({ label: "Frequency", value: "Daily" });
  if (frequency === "scheduled_sessions") metrics.push({ label: "Frequency", value: "Rehab days" });
  return { steps, safety: consolidatedSafety, metrics, selfPaced: !!dose && Object.keys(dose).length === 0 };
}
