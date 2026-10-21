import type { StructuredBlock } from "@/lib/types";

const RANGE: Record<string, string> = {
  floor_level: "Floor level only",
  comfortable_within_clinician_restrictions: "Comfortable range within clinician restrictions",
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

/** Rehab stop_rules also contain dose/range limits, not only symptom triggers. */
export function RehabExerciseLimits({ rules }: { rules: string[] }) {
  return <div className="ex-detail-stop">
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
    </svg>
    <div><span className="sp-stat-label">Exercise limits</span>
      <ul className="sp-cues">{rules.map(rule => <li key={rule}>{rule}</li>)}</ul>
    </div>
  </div>;
}

/** Display the approved fields only; never derive a dose from bank metadata. */
export function RehabPrescription({ block }: { block: StructuredBlock }) {
  if (block.block_type !== "rehab") return null;
  const equipment = block.drill_snapshot?.equipment;
  const words = (value: string) => value.replaceAll("_", " ");
  const resistance = block.resistance?.mode === "bodyweight" ? "Bodyweight only · no added resistance"
    : block.resistance?.mode === "external_kg" && typeof block.resistance.kg === "number"
      ? `${block.resistance.kg} kg` : null;
  const rows = [
    ...(equipment ? [{ label: "Equipment", text: equipment.length ? equipment.map(words).join(", ") : "No equipment needed" }] : []),
    ...(resistance ? [{ label: "Resistance", text: resistance }] : []),
    ...(block.range_choice ? [{ label: "Range", text: RANGE[block.range_choice] ?? words(block.range_choice) }] : []),
    ...(block.frequency === "daily" ? [{ label: "Frequency", text: "Once daily" }] : []),
  ];
  return <>
    {rows.map(row => <p className="sp-block-aside" key={row.label}>
      <span className="sp-stat-label">{row.label}</span>{row.text}
    </p>)}
    {block.mandatory_restrictions?.length ? <div className="sp-block-aside">
      <span className="sp-stat-label">Restrictions</span>
      <ul className="sp-cues">{block.mandatory_restrictions.map(rule => <li key={rule}>{RESTRICTIONS[rule] ?? words(rule)}</li>)}</ul>
    </div> : null}
  </>;
}
