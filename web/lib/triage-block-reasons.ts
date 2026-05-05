export type InjuryTriageSignals = {
  red_flags: string[];
  matched_high_risk_categories: string[];
};

const TRIAGE_SIGNAL_EXPLANATIONS: Record<string, string> = {
  loss_of_consciousness: "You reported a blackout or loss of consciousness. That needs medical review before normal camp work.",
  breathing_pain: "Breathing pain was reported. Contact work can make this worse, so camp is paused.",
  vomiting_after_head_impact: "Vomiting after head impact was reported. That is treated as urgent and needs review first.",
  fracture: "A fracture signal is active. Hard contact is not safe until this is cleared.",
  stress_fracture: "A stress-fracture signal is active. Load must stay controlled until clearance.",
  dislocation: "A dislocation signal is active. Return to contact needs clearance and stable function.",
  acl_tear: "A major knee-ligament signal is active. Hard sparring is paused to protect the joint.",
};

function titleizeToken(value: string) {
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
