export type InjuryTriageSignals = {
  mode?: string;
  reasons?: string[];
  red_flags: string[];
  matched_high_risk_categories: string[];
  routing_reasons?: string[];
  urgent_flags?: string[];
  sparring_risk_band?: string;
  clinician_clearance_required?: boolean;
};
export type GuidedInjurySummary = {
  area?: string;
  injury_type?: string;
  surface_type?: string;
  severity?: string;
  trend?: string;
  impact_related?: string;
  notes?: string;
};

const INJURY_TYPE_LABELS: Record<string, string> = {
  sprain: "Sprain",
  strain: "Strain",
  instability: "Instability",
  fracture: "Fracture",
  dislocation: "Dislocation",
  tendon_ligament: "Tendon or ligament injury",
  post_surgery: "Post-surgery injury",
  head_impact: "Head impact",
  nerve_symptoms: "Nerve symptoms",
  chest_breathing: "Chest or breathing pain",
  pain: "Pain",
  soreness: "Soreness",
  tightness: "Tightness",
  swelling: "Swelling",
  contusion: "Contusion",
  bruise: "Bruise",
  surface_injury: "Surface injury",
};

const SURFACE_TYPE_LABELS: Record<string, string> = {
  cut: "Cut / wound",
  laceration: "Laceration / deep cut",
  abrasion: "Graze / abrasion / mat burn",
  blister: "Blister",
  bruise: "Bruise / contusion",
  contusion: "Bruise / contusion",
  burn: "Burn / skin irritation",
  skin_irritation: "Burn / skin irritation",
};

function formatGuidedInjuryContext(injury: GuidedInjurySummary) {
  const area = titleizeToken(injury.area || "");
  const surfaceKey = injury.surface_type?.trim().toLowerCase() || "";
  const typeKey = injury.injury_type?.trim().toLowerCase() || "";
  const typeLabel =
    SURFACE_TYPE_LABELS[surfaceKey] ||
    titleizeToken(surfaceKey) ||
    INJURY_TYPE_LABELS[typeKey] ||
    titleizeToken(typeKey);
  const meta = [
    injury.severity ? titleizeToken(injury.severity) : null,
    injury.trend ? titleizeToken(injury.trend) : null,
    injury.impact_related === "yes" ? "Impact-related" : null,
  ].filter(Boolean);
  const main = [area, typeLabel].filter(Boolean).join(" — ");
  if (!main) return null;
  return `${main}${meta.length ? ` · ${meta.join(" · ")}` : ""}`;
}

const INJURY_REASON_SYNONYMS: Array<{ label: string; patterns: RegExp[] }> = [
  { label: "Fracture", patterns: [/\bfracture\b/i, /\bbroken\s+bone\b/i, /\bstress\s+fracture\b/i] },
  { label: "Dislocation", patterns: [/\bdislocation\b/i, /\bdislocated\b/i, /\bsublux(?:ation)?\b/i] },
  { label: "Sprain", patterns: [/\bsprain\b/i, /\brolled\s+ankle\b/i, /\btwisted\s+ankle\b/i] },
  { label: "Strain", patterns: [/\bstrain\b/i, /\bpulled\s+muscle\b/i] },
  { label: "Instability", patterns: [/\binstability\b/i, /\bgiving\s+way\b/i, /\bunstable\b/i] },
  { label: "Head impact", patterns: [/\bconcussion\b/i, /\bhead\s+impact\b/i, /\bknocked\s+out\b/i] },
  { label: "Nerve symptoms", patterns: [/\bnumb(?:ness)?\b/i, /\btingl(?:e|ing)\b/i, /\bnerve\b/i] },
  { label: "Chest or breathing pain", patterns: [/\bchest\s+pain\b/i, /\bshort(ness)?\s+of\s+breath\b/i, /\bbreathing\s+pain\b/i] },
  { label: "Surface injury", patterns: [/\bcut\b/i, /\blaceration\b/i, /\babrasion\b/i, /\bblister\b/i, /\bwound\b/i] },
  { label: "Swelling", patterns: [/\bswell(?:ing)?\b/i, /\binflammation\b/i] },
];

function inferInjuryReasonFromText(value: string): string | null {
  const text = value.trim();
  if (!text) return null;
  for (const candidate of INJURY_REASON_SYNONYMS) {
    if (candidate.patterns.some((pattern) => pattern.test(text))) {
      return candidate.label;
    }
  }
  return null;
}

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
  uncontrolled_bleeding: "Uncontrolled bleeding was reported. Planning is paused until this is managed.",
  open_wound: "An open wound was reported. Contact planning is paused until reviewed.",
  infection_signs: "Infection signs were reported. Planning is paused until reviewed.",
  needs_stitches: "A wound that may need stitches was reported. Planning is paused until reviewed.",
  eye_area_wound: "An eye-area wound was reported. Contact planning is paused for safety.",
  sensitive_area_wound: "A wound near a sensitive area was reported. Contact planning is paused until reviewed.",
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

export function summarizeBlockedInjuryContext({
  triage,
  injuriesText,
  guidedInjuries,
}: {
  triage: InjuryTriageSignals;
  injuriesText?: string | null;
  guidedInjuries?: GuidedInjurySummary[] | null;
}) {
  const guidedContext = (guidedInjuries ?? []).map(formatGuidedInjuryContext).find(Boolean);
  const highRiskLabels = [...new Set((triage.matched_high_risk_categories ?? []).map(titleizeToken).filter(Boolean))].slice(0, 2);
  const redFlagLabels = [...new Set((triage.red_flags ?? []).map(titleizeToken).filter(Boolean))].slice(0, 2);
  const urgentFlagLabels = [...new Set((triage.urgent_flags ?? []).map(titleizeToken).filter(Boolean))].slice(0, 2);
  const reasonLabels = [...new Set((triage.reasons ?? []).map((reason) => reason.trim()).filter(Boolean))].slice(0, 2);
  const areas = [...new Set((guidedInjuries ?? [])
    .map((injury) => (typeof injury.area === "string" ? injury.area.trim() : ""))
    .filter(Boolean))]
    .slice(0, 2);
  const guidedTypes = [...new Set((guidedInjuries ?? [])
    .map((injury) => {
      const key = typeof injury.injury_type === "string" ? injury.injury_type.trim().toLowerCase() : "";
      return key ? (INJURY_TYPE_LABELS[key] ?? "") : "";
    })
    .filter(Boolean))]
    .slice(0, 2);
  const injuryLine = typeof injuriesText === "string" ? injuriesText.trim() : "";
  const inferredFromText = inferInjuryReasonFromText(injuryLine);
  const inferredFromGuidedNotes = [...new Set((guidedInjuries ?? [])
    .map((injury) => (typeof injury.notes === "string" ? inferInjuryReasonFromText(injury.notes) : null))
    .filter((value): value is string => Boolean(value)))]
    .slice(0, 2);
  const safetySignals = [
    ...highRiskLabels,
    ...redFlagLabels,
    ...urgentFlagLabels,
    ...reasonLabels,
    ...(inferredFromText ? [inferredFromText] : []),
    ...inferredFromGuidedNotes,
  ];
  const uniqueSafetySignals = [...new Set(safetySignals)].filter(Boolean);
  if (guidedContext && uniqueSafetySignals.length) {
    return `Blocked trigger: ${uniqueSafetySignals.slice(0, 2).join(" + ")} · Captured injury: ${guidedContext}`;
  }
  if (guidedContext) {
    return `Captured injury: ${guidedContext}`;
  }

  const allOrdered = [...new Set([
    ...highRiskLabels,
    ...redFlagLabels,
    ...urgentFlagLabels,
    ...reasonLabels,
    ...guidedTypes,
    ...(inferredFromText ? [inferredFromText] : []),
    ...inferredFromGuidedNotes,
    ...(injuryLine ? [injuryLine] : []),
    ...areas,
  ])];
  const primary = allOrdered[0] ?? null;
  const secondary = allOrdered[1] ?? null;

  if (primary && secondary) {
    return `Blocked trigger: ${primary} + ${secondary}`;
  }
  if (primary) {
    return `Blocked trigger: ${primary}`;
  }
  return "Blocked trigger: Protected planner state";
}
