import type { SparringDayClass, EffectiveLoad } from "@/lib/types";

export type SparringReasonExplanation = {
  title: string;
  body: string;
};

const REASON_EXPLANATIONS: Record<string, SparringReasonExplanation> = {
  high_fatigue: {
    title: "High self-reported fatigue",
    body:
      "You flagged fatigue as high. Hard sparring under high fatigue is harder to recover from and increases injury risk, so the planner pulls back the load on this day.",
  },
  moderate_fatigue: {
    title: "Moderate fatigue load",
    body:
      "Moderate fatigue raises the cost of hard sparring. The planner softens the day so freshness for the next quality session is protected.",
  },
  high_cut: {
    title: "Aggressive weight cut",
    body:
      "Your weight cut is aggressive (3%+ of bodyweight). Hard sparring while cutting hard drains recovery and risks performance loss closer to the fight.",
  },
  moderate_cut: {
    title: "Moderate weight cut",
    body:
      "A moderate cut still pulls on recovery. The planner trims sparring intensity to keep your weight management on track.",
  },
  high_week_pressure: {
    title: "High weekly pressure",
    body:
      "Total weekly load (sparring + S&C + skills) is already high. Adding another hard sparring day on top increases the chance of a stalled adaptation or injury.",
  },
  moderate_week_pressure: {
    title: "Moderate weekly pressure",
    body:
      "Weekly load is meaningful. The planner is keeping headroom so you can hit your hardest day fresh.",
  },
  high_injury: {
    title: "High-severity injury reported",
    body:
      "An injury you flagged is rated high-severity. Hard sparring would expose the affected region to forces it isn't ready to absorb yet.",
  },
  moderate_injury: {
    title: "Moderate injury reported",
    body:
      "A moderate injury is open in your intake. The planner reduces hard exposure until the issue settles or you confirm clearance.",
  },
  worsening: {
    title: "Injury reported as worsening",
    body:
      "You marked the injury trend as worsening. The planner takes the conservative read and softens contact until it stabilises.",
  },
  instability: {
    title: "Joint or tissue instability",
    body:
      "Instability descriptors (e.g. \"giving way\", \"unstable\") were detected. Hard contact magnifies instability risk, so this day is downgraded.",
  },
  daily_symptoms: {
    title: "Daily symptoms reported",
    body:
      "The injury produces daily symptoms. The planner avoids stacking heavy contact on a region that hasn't quieted down yet.",
  },
  two_hard_days: {
    title: "Two hard days already declared",
    body:
      "You declared two or more hard sparring days this week. The planner is balancing intensity so each hard day can hit its target effort.",
  },
  four_hard_days: {
    title: "Four+ hard days declared",
    body:
      "Four or more hard sparring days in one week is well above safe weekly hard exposure for almost every athlete. The planner trims to a sustainable load.",
  },
  consecutive_hard_days: {
    title: "Back-to-back hard sparring",
    body:
      "Hard sparring on consecutive calendar days does not give the central nervous system time to recover. The planner converts the second day to technical or reduced contact.",
  },
  hard_day_cap: {
    title: "Hard-day cap reached",
    body:
      "You're at the planner's weekly cap for effective hard sparring. Additional declared hard days are reframed as managed technical rounds.",
  },
  fight_week_taper: {
    title: "Fight-week taper",
    body:
      "Final taper week. Volume and intensity drop sharply so you arrive sharp, fresh, and rehydrated on fight night.",
  },
  final_week_sparring_cap: {
    title: "Final-week sparring cap",
    body:
      "Final taper week is capped at one effective hard sparring day. Extra declared hard days become technical or reduced-contact work to protect freshness.",
  },
  d14_hard_sparring_ban: {
    title: "Hard sparring cutoff",
    body: "From D-14, declared hard sparring converts to the existing technical or rhythm work. This scheduling rule does not provide medical clearance.",
  },
  serious_contact_safety: {
    title: "No contact or sparring",
    body: "A serious safety concern requires medical evaluation and the appropriate clearance pathway before contact resumes.",
  },
  medical_contact_restriction: {
    title: "Contact restricted",
    body: "Follow the active no-contact restriction. The fight countdown does not clear it.",
  },
  d17_hard_sparring_ban: {
    title: "Earlier hard sparring cutoff",
    body:
      "Elevated risk brings hard-sparring conversion forward to D-17. The session keeps its existing technical or rhythm format.",
  },
  d21_d18_cap_one: {
    title: "D-21 to D-18 single hard day",
    body:
      "Between D-21 and D-18 the planner allows at most one hard sparring day. The rest is technical or sharpness work to protect peaking.",
  },
};

const LOAD_EXPLANATIONS: Record<EffectiveLoad, SparringReasonExplanation> = {
  hard: {
    title: "Effective load: Hard",
    body:
      "Full-contact, full-intensity sparring. Plan recovery, hydration, and downstream sessions around protecting this day.",
  },
  technical: {
    title: "Effective load: Technical / rhythm",
    body:
      "Controlled rounds at lower intensity. Focus is positional sharpness, timing, and reads — not concussive output.",
  },
  reduced: {
    title: "Effective load: Reduced",
    body:
      "Volume or intensity has been pulled back from what you declared. This usually reflects fatigue, weight cut, injury, or weekly pressure caps.",
  },
  none: {
    title: "Effective load: None",
    body: "No sparring is scheduled for this day.",
  },
};

const CLASS_EXPLANATIONS: Record<SparringDayClass, SparringReasonExplanation> = {
  primary_hard: {
    title: "Primary hard day",
    body:
      "This is the hardest sparring day of the week — your peak effective output. The rest of the week is shaped to protect it.",
  },
  secondary_hard: {
    title: "Secondary hard day",
    body:
      "A second hard sparring day, intentionally separated from the primary day so each can land at full quality.",
  },
  managed_hard: {
    title: "Managed hard day",
    body:
      "Declared as hard, but the planner has dialled it back due to fatigue, injury, weekly pressure, or a fight-week cap. Treat as quality technical work.",
  },
  technical: {
    title: "Technical / rhythm day",
    body:
      "Sub-maximal sparring focused on timing, distance, reads, and movement quality. Not the day to test power.",
  },
  none: {
    title: "No sparring scheduled",
    body: "No sparring is scheduled for this day in the active block.",
  },
};

const RISK_BAND_EXPLANATIONS: Record<string, SparringReasonExplanation> = {
  green: {
    title: "Green band — proceed",
    body:
      "Risk signals are clear. The planner is comfortable with hard sparring as declared, assuming the rest of the camp checks stay clean.",
  },
  amber: {
    title: "Amber band — caution",
    body:
      "One or more caution signals are active (fatigue, weight cut, mild injury, weekly pressure). The planner suggests softening hard sparring until the signal clears.",
  },
  red: {
    title: "Red band — pull back",
    body:
      "Multiple meaningful risk signals are active. Hard sparring as declared is likely to cost more than it earns. The planner recommends technical work or deload.",
  },
  black: {
    title: "Black band — stop & reassess",
    body:
      "Severe injury or stacked high-severity signals are present. The planner blocks hard sparring outright and routes the camp through review.",
  },
};

function humanizeUnknownCode(code: string): SparringReasonExplanation {
  const cleaned = code.replace(/_/g, " ").trim();
  const title = cleaned ? cleaned.charAt(0).toUpperCase() + cleaned.slice(1) : code;
  return {
    title,
    body:
      "The planner flagged this as a sparring decision factor. Open the coach review notes for the full rationale.",
  };
}

export function explainReasonCode(code: string): SparringReasonExplanation {
  const direct = REASON_EXPLANATIONS[code];
  if (direct) {
    return direct;
  }
  return humanizeUnknownCode(code);
}

export function explainEffectiveLoad(load: EffectiveLoad): SparringReasonExplanation {
  return LOAD_EXPLANATIONS[load] ?? LOAD_EXPLANATIONS.none;
}

export function explainSparringClass(value: SparringDayClass): SparringReasonExplanation {
  return CLASS_EXPLANATIONS[value] ?? CLASS_EXPLANATIONS.none;
}

export function explainRiskBand(band: string | null | undefined): SparringReasonExplanation | null {
  if (!band) {
    return null;
  }
  return RISK_BAND_EXPLANATIONS[band] ?? null;
}

export function knownReasonCodes(): string[] {
  return Object.keys(REASON_EXPLANATIONS);
}
