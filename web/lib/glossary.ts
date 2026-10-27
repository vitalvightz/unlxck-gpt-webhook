// Plain-English definitions for the coaching jargon the plan surfaces print.
//
// The plan renderer speaks S&C shorthand ("RPE 7", "AMRAP", "Prehab") that a
// fighter reading their own plan has no reason to know. Every term here is
// rendered with an "i" affordance, so the
// definition is one tap away instead of something the athlete has to look up.
//
// Keep definitions to one or two sentences: the bubble is a glance, not a
// lesson. Add a term only when the label itself is opaque. Plain words like
// Duration, Rest or Swaps do not belong here, and an "i" on every label would
// bury the ones that matter.

export type GlossaryEntry = {
  /** Heading shown in the tooltip bubble. */
  term: string;
  definition: string;
};

/**
 * Keyed by the lowercased term as it is rendered on screen, so a caller can pass
 * the label it is already printing (`Volume`, `Stop rule`, a Rehab/Prehab tag)
 * and get a definition only when one exists.
 *
 * The effort keys are the EffortMethod enum values from
 * api/structured_plan_models.py, because a block's effort card is glossed from
 * block.effort.method, never from the word "Effort". A block prescribing
 * "Max intent" or "RIR 2" must not be explained with the RPE scale. There is
 * deliberately NO "effort" entry: the label alone does not say which scale is in
 * play, so an unrecognised method renders no tooltip at all.
 *
 * Careful with `intent`: it is an EffortMethod here (how fast you try to move),
 * and ALSO a mindset-anchor label meaning something entirely different. The
 * mindset card renders no tooltips for that reason; gloss it from a label and it
 * would explain a focus cue as bar speed.
 */
const GLOSSARY: Readonly<Record<string, GlossaryEntry>> = {
  rpe: {
    term: "RPE",
    definition:
      "How hard the work should feel, from 1 (very easy) to 10 (max). RPE 7–8 is hard but controlled; 3 or below is easy recovery.",
  },
  rir: {
    term: "RIR",
    definition:
      "Reps In Reserve: how many more reps you should have left when you rack the set. RIR 2 means stopping with 2 clean reps still in you; RIR 0 means going to failure.",
  },
  intent: {
    term: "Intent",
    definition:
      "How hard you try to move, not how heavy the load is. Max intent means driving every rep as fast as possible, even when light.",
  },
  velocity: {
    term: "Velocity",
    definition:
      "Bar or limb speed, usually in metres per second. Hold the prescribed speed; drop the load once you fall below it instead of grinding.",
  },
  heart_rate_zone: {
    term: "Heart rate zone",
    definition:
      "The heart-rate band to stay in. Zones 1-2 are conversational, 3-4 are hard breathing, 5 is near max.",
  },
  pace: {
    term: "Pace",
    definition:
      "The speed to hold, usually time per kilometre or round. Pace is the target; let effort rise and fall with terrain or fatigue.",
  },
  max_effort_percent: {
    term: "Max effort %",
    definition:
      "A percentage of your max for this movement. 90% is near your top end; 60% is comfortable, repeatable work.",
  },
  load: {
    term: "Load",
    definition:
      "How heavy to go: a weight, a percentage of the heaviest single rep you could manage (1RM), or a cue like bodyweight. Pick the load that lets you hit the target effort with clean technique.",
  },
  volume: {
    term: "Volume",
    definition:
      "How much work to do. For example, 3 × 8 means 8 reps, rest, then repeat for 3 sets.",
  },
  mode: {
    term: "Mode",
    definition:
      "How the work is paced. Continuous = no breaks. AMRAP = as many rounds or reps as possible in the time. EMOM = every minute on the minute: start each set at the top of the minute.",
  },
  rehab: {
    term: "Rehab",
    definition:
      "Targeted work for a current injury that settles and rebuilds the area. Shorten or skip it on painful days, and stay well inside pain-free range.",
  },
  prehab: {
    term: "Prehab",
    definition:
      "Rehab work kept in the plan after an injury clears so it doesn't return. Preventative, not treatment.",
  },
  mobility: {
    term: "Mobility",
    definition:
      "Moving a joint through its full range under your own control. Preparation and maintenance, not stretching for its own sake.",
  },
  "stop rule": {
    term: "Stop rule",
    definition:
      "When to stop this block early. If it happens, stop. Finishing isn't worth injury or illness.",
  },
  deload: {
    term: "Deload",
    definition:
      "A planned easy week. Working sets roughly halve and loads stay light so recent training turns into adaptation.",
  },
  taper: {
    term: "Taper",
    definition:
      "Training volume drops before the fight so you arrive fresh but still sharp.",
  },
  gpp: {
    term: "GPP",
    definition:
      "General Physical Preparation: building a broad base of strength, fitness and durability.",
  },
  spp: {
    term: "SPP",
    definition:
      "Specific Physical Preparation: training shifts to match the demands of your fight.",
  },
};

/** The definition for a rendered label, or null when the label needs no gloss. */
export function glossaryEntry(term: string | null | undefined): GlossaryEntry | null {
  if (typeof term !== "string") {
    return null;
  }
  return GLOSSARY[term.trim().toLowerCase()] ?? null;
}
