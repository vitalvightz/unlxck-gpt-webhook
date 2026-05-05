export type InjuryTriageSignals = {
  red_flags: string[];
  matched_high_risk_categories: string[];
};

const TRIAGE_SIGNAL_EXPLANATIONS: Record<string, string> = {
  loss_of_consciousness: "You reported a blackout or loss of consciousness. That needs medical review before normal camp work.",
  breathing_pain: "Breathing pain was reported. Contact work can make this worse, so camp is paused.",
  vomiting_after_head_impact: "Vomiting after head impact was reported. That is treated as urgent and needs review first.",
  severe_headache_after_head_impact: "A severe headache after head impact was reported. We stop contact and get this reviewed first.",
  seizure_or_convulsion: "A seizure or convulsion signal was reported. This needs urgent medical review before training resumes.",
  amnesia_or_memory_loss: "Memory-loss symptoms were reported after impact. Contact work is paused for safety.",
  chest_pain: "Chest pain was reported. Hard loading is paused until this is reviewed.",
  shortness_of_breath: "Breathing symptoms were reported. Contact work is paused until reviewed.",
  pneumothorax: "A chest/lung risk signal is active. This requires medical clearance before progression.",
  hemothorax: "A chest bleed risk signal is active. Training is paused until medical clearance.",
  fracture: "A fracture signal is active. Hard contact is not safe until this is cleared.",
  stress_fracture: "A stress-fracture signal is active. Load must stay controlled until clearance.",
  rib_fracture: "A rib fracture signal is active. Contact and heavy breathing stress must stay restricted.",
  broken_rib: "A broken-rib signal is active. Contact work is paused to protect healing.",
  open_fracture: "An open-fracture signal is active. This needs urgent medical management before planning can continue.",
  dislocation: "A dislocation signal is active. Return to contact needs clearance and stable function.",
  achilles_rupture: "An Achilles rupture signal is active. Impact loading must stay restricted.",
  full_thickness_rotator_cuff_tear: "A full-thickness shoulder tear signal is active. Contact work is paused until cleared.",
  tendon_rupture_or_avulsion: "A tendon rupture or avulsion signal is active. Full-contact work is blocked for safety.",
  acl_tear: "A major knee-ligament signal is active. Hard sparring is paused to protect the joint.",
};

export function titleizeToken(value: string) {
  const cleaned = value.replace(/_/g, " ").trim();
  return cleaned ? cleaned.charAt(0).toUpperCase() + cleaned.slice(1) : "";
}

export function buildBlockedWhy(triage: InjuryTriageSignals): { title: string; body: string } {
  const signals = [...triage.red_flags, ...triage.matched_high_risk_categories].filter(Boolean);
  const topSignals = signals.slice(0, 2);

  if (!topSignals.length) {
    return {
      title: "Why this was paused",
      body: "Coach call: your intake triggered a safety hold, so we paused normal planning until review is complete.",
    };
  }

  const reasons = topSignals.map(
    (signal) =>
      TRIAGE_SIGNAL_EXPLANATIONS[signal] ??
      `${titleizeToken(signal)} was flagged and needs review before hard loading resumes.`,
  );

  return {
    title: "Why this was blocked",
    body: `Coach call: ${reasons.join(" ")}`,
  };
}
