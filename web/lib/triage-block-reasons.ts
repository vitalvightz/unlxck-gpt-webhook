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
  avoid?: string;
  timeframe?: string;
  cleared?: string;
  open_wound?: string;
  bleeding_status?: string;
  infection_signs?: string[];
  sensitive_area?: string;
};

export type CapturedInjuryDetail = {
  headline: string;
  meta: string[];
  notes?: string;
  avoid?: string;
  flags: string[];
};

export type BlockedInjuryContextSummary = {
  capturedInjury?: string;
  blockedTrigger?: string;
  capturedInjuries?: CapturedInjuryDetail[];
  pauseReasons?: string[];
  legacyInjuryText?: string;
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
    (surfaceKey ? titleizeToken(surfaceKey) : "") ||
    INJURY_TYPE_LABELS[typeKey] ||
    titleizeToken(typeKey);
  if (!typeLabel) return null;
  const meta = [
    injury.severity ? titleizeToken(injury.severity) : null,
    injury.trend ? titleizeToken(injury.trend) : null,
    injury.impact_related === "yes" ? "Impact-related" : null,
  ].filter(Boolean);
  const main = [area, typeLabel].filter(Boolean).join(" — ");
  if (!main) return null;
  return `${main}${meta.length ? ` · ${meta.join(" · ")}` : ""}`;
}

function _tokenizeSignal(value: string): string[] {
  return value
    .toLowerCase()
    .replace(/[_-]/g, " ")
    .split(/[^a-z0-9]+/)
    .map((token) => token.trim())
    .filter((token) => token.length >= 3);
}

function selectGuidedInjuryContext(
  guidedInjuries: GuidedInjurySummary[],
  triage: InjuryTriageSignals,
): string | null {
  const signals = [
    ...(triage.red_flags ?? []),
    ...(triage.matched_high_risk_categories ?? []),
    ...(triage.urgent_flags ?? []),
    ...(triage.reasons ?? []),
    ...(triage.routing_reasons ?? []),
  ]
    .filter((value): value is string => typeof value === "string" && Boolean(value.trim()))
    .map((value) => value.trim().toLowerCase());

  const signalTokens = new Set(signals.flatMap(_tokenizeSignal));

  const scored = guidedInjuries
    .map((injury, index) => {
      const context = formatGuidedInjuryContext(injury);
      if (!context) return null;
      const fields = [
        { value: injury.notes, weight: 2 },
        { value: injury.injury_type, weight: 3 },
        { value: injury.surface_type, weight: 3 },
        { value: injury.area, weight: 3 },
      ]
        .filter((field): field is { value: string; weight: number } => typeof field.value === "string" && Boolean(field.value.trim()))
        .map((field) => ({ value: field.value.trim().toLowerCase(), weight: field.weight }));

      let score = 0;
      for (const field of fields) {
        for (const token of _tokenizeSignal(field.value)) {
          if (signalTokens.has(token)) {
            score += field.weight;
          }
        }
      }

      return { context, index, score };
    })
    .filter((entry): entry is { context: string; index: number; score: number } => Boolean(entry));

  if (!scored.length) return null;

  const best = scored.reduce((top, current) => {
    if (!top) return current;
    if (current.score > top.score) return current;
    if (current.score === top.score && current.index < top.index) return current;
    return top;
  }, null as { context: string; index: number; score: number } | null);

  if (!best) return null;
  if (best.score <= 0) {
    return scored[0]?.context ?? null;
  }
  return best.context;
}

export function buildCapturedInjuryDetail(
  injury: GuidedInjurySummary,
): CapturedInjuryDetail | null {
  const area = titleizeToken(injury.area || "");
  const surfaceKey = injury.surface_type?.trim().toLowerCase() || "";
  const typeKey = injury.injury_type?.trim().toLowerCase() || "";
  const typeLabel =
    SURFACE_TYPE_LABELS[surfaceKey] ||
    (surfaceKey ? titleizeToken(surfaceKey) : "") ||
    INJURY_TYPE_LABELS[typeKey] ||
    titleizeToken(typeKey);
  const headline = [area, typeLabel].filter(Boolean).join(" — ");
  if (!headline) return null;

  const meta = [
    injury.severity ? `${titleizeToken(injury.severity)} severity` : null,
    injury.trend ? `Trend: ${titleizeToken(injury.trend)}` : null,
    injury.impact_related === "yes" ? "Impact-related" : null,
    injury.timeframe ? `Onset: ${titleizeToken(injury.timeframe)}` : null,
  ].filter((value): value is string => Boolean(value));

  const bleedingKey = injury.bleeding_status?.trim().toLowerCase() || "";
  const infectionSigns = (injury.infection_signs ?? [])
    .map((sign) => (typeof sign === "string" ? sign.trim() : ""))
    .filter(Boolean);
  const clearedKey = injury.cleared?.trim().toLowerCase() || "";

  const flags = [
    injury.open_wound === "yes" ? "Open wound" : null,
    bleedingKey && bleedingKey !== "none"
      ? `Bleeding: ${titleizeToken(bleedingKey)}`
      : null,
    infectionSigns.length
      ? `Infection signs: ${infectionSigns.map(titleizeToken).join(", ")}`
      : null,
    injury.sensitive_area === "yes" ? "Sensitive area" : null,
    clearedKey === "no"
      ? "Not yet medically cleared"
      : clearedKey === "yes"
        ? "Medically cleared"
        : null,
  ].filter((value): value is string => Boolean(value));

  const notes = injury.notes?.trim();
  const avoid = injury.avoid?.trim();

  const detail: CapturedInjuryDetail = { headline, meta, flags };
  if (notes) detail.notes = notes;
  if (avoid) detail.avoid = avoid;
  return detail;
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
  eye_area_wound: "An eye-area wound was reported. Contact planning is paused until reviewed.",
  sensitive_area_wound: "A wound near a sensitive area was reported. Contact planning is paused until reviewed.",
};

export function titleizeToken(value: string) {
  const cleaned = value.replace(/_/g, " ").trim();
  return cleaned ? cleaned.charAt(0).toUpperCase() + cleaned.slice(1) : "";
}

export function buildBlockedWhy(triage: InjuryTriageSignals): { title: string; body: string } {
  const signals = [...triage.red_flags, ...triage.matched_high_risk_categories].filter(Boolean);
  const topSignals = signals.slice(0, 2);
  const mode = (triage.mode || "").trim().toLowerCase();

  const prefixByMode =
    mode === "medical_hold"
      ? "Medical hold: this requires medical/clinical review before training guidance continues."
      : mode === "restricted_rehab_only"
        ? "Normal fight-camp loading is blocked. Only restricted rehab/support guidance is allowed until cleared."
        : mode === "needs_review"
          ? "Coach/admin review is required before normal plan generation continues."
          : "Coach call: your intake triggered a safety hold, so we paused normal planning until review is complete.";

  if (!topSignals.length) {
    return {
      title: "Why this was paused",
      body: prefixByMode,
    };
  }

  const reasons = topSignals.map(
    (signal) =>
      TRIAGE_SIGNAL_EXPLANATIONS[signal] ??
      `${titleizeToken(signal)} was flagged and needs review before hard loading resumes.`,
  );

  return {
    title: "Why this was blocked",
    body: `${prefixByMode} ${reasons.join(" ")}`,
  };
}

export function buildBlockedInjuryContextSummary({
  triage,
  injuriesText,
  guidedInjuries,
}: {
  triage: InjuryTriageSignals;
  injuriesText?: string | null;
  guidedInjuries?: GuidedInjurySummary[] | null;
}): BlockedInjuryContextSummary {
  const guidedContext = selectGuidedInjuryContext(guidedInjuries ?? [], triage);
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
    ...redFlagLabels,
    ...urgentFlagLabels,
    ...highRiskLabels,
    ...reasonLabels,
    ...(inferredFromText ? [inferredFromText] : []),
    ...inferredFromGuidedNotes,
  ];
  const uniqueSafetySignals = [...new Set(safetySignals)].filter(Boolean);

  const capturedInjuries = (guidedInjuries ?? [])
    .map(buildCapturedInjuryDetail)
    .filter((detail): detail is CapturedInjuryDetail => Boolean(detail));
  const pauseReasons = [
    ...new Set(
      (triage.reasons ?? [])
        .map((reason) => (typeof reason === "string" ? reason.trim() : ""))
        .filter(Boolean),
    ),
  ];

  const attachExtras = (
    base: BlockedInjuryContextSummary,
  ): BlockedInjuryContextSummary => {
    const extras: Partial<BlockedInjuryContextSummary> = {};
    if (capturedInjuries.length) {
      extras.capturedInjuries = capturedInjuries;
    } else if (injuryLine) {
      extras.legacyInjuryText = injuryLine;
    }
    if (pauseReasons.length) {
      extras.pauseReasons = pauseReasons;
    }
    return { ...base, ...extras };
  };

  if (guidedContext) {
    const result: BlockedInjuryContextSummary = { capturedInjury: guidedContext };
    if (uniqueSafetySignals.length) {
      result.blockedTrigger = uniqueSafetySignals.slice(0, 2).join(" + ");
    }
    return attachExtras(result);
  }

  const allOrdered = [...new Set([
    ...redFlagLabels,
    ...urgentFlagLabels,
    ...highRiskLabels,
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
    return attachExtras({ blockedTrigger: `${primary} + ${secondary}` });
  }
  if (primary) {
    return attachExtras({ blockedTrigger: primary });
  }
  return attachExtras({ blockedTrigger: "Protected planner state" });
}

export function summarizeBlockedInjuryContext(input: {
  triage: InjuryTriageSignals;
  injuriesText?: string | null;
  guidedInjuries?: GuidedInjurySummary[] | null;
}) {
  const summary = buildBlockedInjuryContextSummary(input);
  const parts: string[] = [];
  if (summary.capturedInjury) {
    parts.push(`Captured injury: ${summary.capturedInjury}`);
  }
  if (summary.blockedTrigger) {
    parts.push(`Blocked trigger: ${summary.blockedTrigger}`);
  }
  return parts.join(" · ");
}
