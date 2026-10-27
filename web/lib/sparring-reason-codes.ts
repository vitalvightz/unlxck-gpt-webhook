import type { SparringDayClass, EffectiveLoad } from "@/lib/types";

export type SparringReasonExplanation = {
  title: string;
  body: string;
};

const REASON_EXPLANATIONS: Record<string, SparringReasonExplanation> = {
  high_fatigue: {
    title: "High self-reported fatigue",
    body:
      "Fatigue is high. Hard sparring when fatigued is harder to recover from and raises injury risk, so this day is lighter.",
  },
  moderate_fatigue: {
    title: "Moderate fatigue load",
    body:
      "Moderate fatigue raises the cost of hard sparring, so the day is softened to keep you fresh for the next quality session.",
  },
  high_cut: {
    title: "Aggressive weight cut",
    body:
      "Your cut is aggressive (3%+ of bodyweight). Hard sparring while cutting drains recovery and risks performance near the fight.",
  },
  moderate_cut: {
    title: "Moderate weight cut",
    body:
      "A moderate cut still taxes recovery, so sparring intensity is trimmed to keep your weight on track.",
  },
  high_week_pressure: {
    title: "High weekly pressure",
    body:
      "Weekly load (sparring + S&C + skills) is already high. Another hard day raises the risk of stalled progress or injury.",
  },
  moderate_week_pressure: {
    title: "Moderate weekly pressure",
    body:
      "Weekly load is high, so headroom is kept for your hardest day.",
  },
  high_injury: {
    title: "High-severity injury reported",
    body:
      "A flagged injury is high-severity. Hard sparring would load the area with forces it can't take yet.",
  },
  moderate_injury: {
    title: "Moderate injury reported",
    body:
      "A moderate injury is open, so hard exposure is reduced until it settles or you confirm clearance.",
  },
  worsening: {
    title: "Injury reported as worsening",
    body:
      "Your injury is worsening, so contact is softened until it stabilises.",
  },
  instability: {
    title: "Joint or tissue instability",
    body:
      "Instability terms (e.g. \"giving way\", \"unstable\") were detected. Hard contact raises instability risk, so this day is downgraded.",
  },
  daily_symptoms: {
    title: "Daily symptoms reported",
    body:
      "The injury causes daily symptoms, so heavy contact is kept off the area until it settles.",
  },
  two_hard_days: {
    title: "Two hard days already declared",
    body:
      "Two or more hard sparring days this week. Intensity is balanced so each hits its target.",
  },
  four_hard_days: {
    title: "Four+ hard days declared",
    body:
      "Four or more hard sparring days a week is well above safe exposure for almost anyone, so it's trimmed to a sustainable load.",
  },
  consecutive_hard_days: {
    title: "Back-to-back hard sparring",
    body:
      "Back-to-back hard sparring days don't let the nervous system recover, so the second becomes technical or reduced contact.",
  },
  hard_day_cap: {
    title: "Hard-day cap reached",
    body:
      "You're at the weekly hard sparring cap. Extra hard days become managed technical rounds.",
  },
  fight_week_taper: {
    title: "Fight-week taper",
    body:
      "Final taper week. Volume and intensity drop sharply so you arrive sharp, fresh and rehydrated.",
  },
  final_week_sparring_cap: {
    title: "Final-week sparring cap",
    body:
      "Final taper week allows one hard sparring day. Extra hard days become technical or reduced-contact work to keep you fresh.",
  },
  d14_hard_sparring_ban: {
    title: "Hard sparring cutoff",
    body: "From D-14, hard sparring becomes technical or rhythm work. This scheduling rule isn't medical clearance.",
  },
  serious_contact_safety: {
    title: "No contact or sparring",
    body: "A serious safety concern needs medical evaluation and clearance before contact resumes.",
  },
  medical_contact_restriction: {
    title: "Contact restricted",
    body: "Follow the active no-contact restriction. The fight countdown does not clear it.",
  },
  d17_hard_sparring_ban: {
    title: "Earlier hard sparring cutoff",
    body:
      "Elevated risk moves hard-sparring conversion forward to D-17. The session keeps its technical or rhythm format.",
  },
  d21_d18_cap_one: {
    title: "D-21 to D-18 single hard day",
    body:
      "From D-21 to D-18, at most one hard sparring day. The rest is technical or sharpness work to protect your peak.",
  },
};

const LOAD_EXPLANATIONS: Record<EffectiveLoad, SparringReasonExplanation> = {
  hard: {
    title: "Effective load: Hard",
    body:
      "Full-contact, full-intensity sparring. Plan recovery, hydration and other sessions around this day.",
  },
  technical: {
    title: "Effective load: Technical / rhythm",
    body:
      "Controlled, lower-intensity rounds for positioning, timing and reads, not power.",
  },
  reduced: {
    title: "Effective load: Reduced",
    body:
      "Volume or intensity is below what you declared, usually due to fatigue, weight cut, injury or weekly load caps.",
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
      "The week's hardest sparring day. The rest of the week is shaped to protect it.",
  },
  secondary_hard: {
    title: "Secondary hard day",
    body:
      "A second hard sparring day, spaced from the primary so each lands at full quality.",
  },
  managed_hard: {
    title: "Managed hard day",
    body:
      "Declared hard, but dialled back for fatigue, injury, weekly load or a fight-week cap. Treat as quality technical work.",
  },
  technical: {
    title: "Technical / rhythm day",
    body:
      "Sub-maximal sparring for timing, distance, reads and movement. Not a day to test power.",
  },
  none: {
    title: "No sparring scheduled",
    body: "No sparring is scheduled for this day in the active block.",
  },
};

const RISK_BAND_EXPLANATIONS: Record<string, SparringReasonExplanation> = {
  green: {
    title: "Green band: proceed",
    body:
      "Risk signals are clear. Hard sparring as declared is fine if other camp checks stay clean.",
  },
  amber: {
    title: "Amber band: caution",
    body:
      "Caution signals are active (fatigue, weight cut, mild injury, weekly load). Soften hard sparring until they clear.",
  },
  red: {
    title: "Red band: pull back",
    body:
      "Several risk signals are active. Hard sparring would likely cost more than it earns. Technical work or a deload is recommended.",
  },
  black: {
    title: "Black band: stop & reassess",
    body:
      "Severe injury or stacked high-severity signals. Hard sparring is blocked and the camp goes to review.",
  },
};

function humanizeUnknownCode(code: string): SparringReasonExplanation {
  const cleaned = code.replace(/_/g, " ").trim();
  const title = cleaned ? cleaned.charAt(0).toUpperCase() + cleaned.slice(1) : code;
  return {
    title,
    body:
      "Flagged as a sparring factor. See coach review notes for why.",
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
