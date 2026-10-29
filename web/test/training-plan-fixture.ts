import type { StructuredPlan, StructuredSession, TodaySessionCompletionRecord } from "../lib/types";

export const strength: StructuredSession = {
  session_id: "strength", title: "Strength & Power", session_type: "strength_power",
  objective: "Build strength with crisp, controlled repetitions.",
  blocks: [
    { block_id: "press", block_type: "strength", display_name: "Landmine Press → Med Ball Chest Pass", sets: 4, reps: 4,
      load: { method: "absolute", value: 15, unit: "kg" }, coaching_cues: ["Brace before each repetition."], stop_rules: ["Stop for sharp shoulder pain."] },
    { block_id: "bounds", block_type: "conditioning", display_name: "Alternating Bounds", rounds: 4,
      work: { value: 120, unit: "seconds" }, rest: { value: 120, unit: "seconds" } },
    { block_id: "squat", block_type: "strength", display_name: "Back Squat", sets: 3, reps: 8,
      effort: { method: "RPE", value: 6 }, load: { method: "absolute", value: 40, unit: "kg" },
      coaching_cues: ["Keep the whole foot planted."], progression_rule: "Keep the same load until every repetition is controlled." },
    { block_id: "row", block_type: "accessory", display_name: "Single-Arm Cable Row With Controlled Return", sets: 3, reps: "8 per side" },
  ],
};
export const recovery: StructuredSession = {
  session_id: "recovery", title: "Joint Prep", session_type: "recovery", objective: "Maintain comfortable, controlled movement.",
  blocks: [{ block_id: "mobility", block_type: "rehab", display_name: "Joint CARs and mobility drills", sets: 2, reps: 5,
    coaching_cues: ["Move slowly through a comfortable range."], mandatory_restrictions: ["Follow clinician restrictions. No contact training."],
    stop_rules: ["Stop if new pain appears or symptoms worsen."], progression_rule: "Do not progress without the prescribed review." }],
};
export const mental: StructuredSession = {
  session_id: "mental", title: "Composure rehearsal", session_type: "skill", planned_duration: { value: 12, unit: "minutes" },
  objective: "Practise recovering your composure when exchanges do not go your way.",
  blocks: [{ block_id: "mental-drill", block_type: "mindset", display_name: "Pressure → Reset",
    coaching_cues: ["Step 1: Picture being caught clean in an exchange.", "Step 2: Exhale, cover, move your feet and rebuild your stance.",
      "Step 3: Picture your best shot being blocked twice in a row.", "Step 4: Change the setup and continue working."],
    instructions: "Rehearse the complete sequence in real time.", progression_rule: "Repeat the same scenario with a different opponent reaction.",
    stop_rules: ["Stop if the rehearsal causes distress."] }],
};
export const trainingPlan: StructuredPlan = {
  schema_version: "1.0", plan_metadata: { title: "Fight camp", sport: "boxing", plan_type: "fight_camp" },
  plan_notes: [{ category: "injury", text: "Follow your clinician's active contact restrictions." }],
  red_flag_rules: [{ rule_id: "safety", display_text: "Stop training if symptoms worsen.", action: "Seek medical review before resuming.", severity: "red" }],
  weeks: Array.from({ length: 8 }, (_, week) => ({
    week_id: `week-${week + 1}`, week_index: week + 1, phase_label: week > 5 ? "TAPER" : "GPP",
    days: Array.from({ length: 7 }, (_, index) => {
      const date = new Date(Date.UTC(2026, 9, 26 + week * 7 + index)).toISOString().slice(0, 10);
      return { date, countdown_label: `D-${56 - week * 7 - index}`, day_type: index === 6 ? "rest" : "moderate",
        today_card: index === 3 ? { headline: "Hard sparring", coach_led_contact: "Hard sparring",
          primary_warning: "Follow coach instructions. No additional contact outside your prescribed rounds.",
          mindset_anchor: { focus_cue: "Follow coach and control impact", context: "No additional S&C prescribed." } } : undefined,
        sessions: index === 3 || index === 6 ? [] : index === 0 ? [strength, recovery] : [index === 4 ? recovery : index === 5 ? mental : strength] };
    }),
  })),
};
export const completions: TodaySessionCompletionRecord[] = [
  { id: "done", athlete_id: "athlete", plan_id: "premium-plan", session_id: "strength", training_day: "2026-10-26", status: "done", session_rpe: 6 },
  { id: "modified", athlete_id: "athlete", plan_id: "premium-plan", session_id: "strength", training_day: "2026-10-27", status: "modified", session_rpe: 5,
    modification_reason: "Changed: Back Squat (3 sets). Kept the coach's original guidance and adjusted prescription." },
];
