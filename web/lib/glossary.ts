// Plain-English definitions for the coaching jargon the plan surfaces print.
//
// The plan renderer speaks S&C shorthand ("RPE 7", "AMRAP", "Prehab") that a
// fighter reading their own plan has no reason to know. Every term here is
// rendered with the same "?" affordance the intake form already uses, so the
// definition is one tap away instead of something the athlete has to look up.
//
// Keep definitions to one or two sentences: the bubble is a glance, not a
// lesson. Add a term only when the label itself is opaque. Plain words like
// Duration, Rest or Swaps do not belong here, and a "?" on every label would
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
 * "intent max" or "RIR 2" must not be explained with the RPE scale. There is
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
      "Rate of Perceived Exertion: how hard the work should feel, from 1 (barely working) to 10 (all-out). Around 7-8 you could still manage 2-3 more reps; anything under 3 is easy, recovery-pace work.",
  },
  rir: {
    term: "RIR",
    definition:
      "Reps In Reserve: how many more reps you should have left when you rack the set. RIR 2 means stopping with 2 clean reps still in you; RIR 0 means going to failure.",
  },
  intent: {
    term: "Intent",
    definition:
      "How hard you try to move, not how heavy the load is. Max intent means driving every rep as fast as you can, even when the weight itself is light.",
  },
  velocity: {
    term: "Velocity",
    definition:
      "Bar or limb speed, usually in metres per second. Hold the prescribed speed and drop the load once you fall below it, rather than grinding slower reps.",
  },
  heart_rate_zone: {
    term: "Heart rate zone",
    definition:
      "The heart-rate band to stay inside. Zones 1-2 are easy aerobic work you could hold a conversation through, zones 3-4 are hard breathing, zone 5 is close to your maximum.",
  },
  pace: {
    term: "Pace",
    definition:
      "The speed to hold, usually time per kilometre or per round. Pace is the target, so let effort rise and fall with terrain or fatigue to keep it honest.",
  },
  max_effort_percent: {
    term: "Max effort %",
    definition:
      "A percentage of your maximum for this movement. 90% sits near your top end; 60% is comfortably submaximal work you can repeat cleanly.",
  },
  load: {
    term: "Load",
    definition:
      "How heavy to go: a weight, a percentage of the heaviest single rep you could manage (1RM), or a cue like bodyweight. Pick the load that lets you hit the target effort with clean technique.",
  },
  volume: {
    term: "Volume",
    definition:
      "How much work to do, written as sets × reps. “3 × 8” means 8 repetitions, rested, then repeated 3 times.",
  },
  mode: {
    term: "Mode",
    definition:
      "How the work is paced rather than how much of it there is. Continuous = keep going without breaks. AMRAP = as many rounds or reps as possible in the time. EMOM = every minute on the minute, start the next set at the top of each minute.",
  },
  rehab: {
    term: "Rehab",
    definition:
      "Targeted work for an injury you are still carrying. It settles the area down and rebuilds it. Shorten or skip it on a day it hurts, and keep it well inside pain-free range.",
  },
  prehab: {
    term: "Prehab",
    definition:
      "The same work as rehab, kept in the plan after an injury has cleared so it does not come back. Preventative, not treatment.",
  },
  mobility: {
    term: "Mobility",
    definition:
      "Controlled range-of-motion work: moving a joint through its full range under your own control. It is preparation and maintenance, not stretching for its own sake.",
  },
  "stop rule": {
    term: "Stop rule",
    definition:
      "The signal to end this block early. If it shows up, stop. Finishing the prescription is never worth the setback.",
  },
  deload: {
    term: "Deload",
    definition:
      "A planned easy week. Working sets drop roughly by half and loads stay light so the training you have already done can turn into adaptation.",
  },
  taper: {
    term: "Taper",
    definition:
      "The run-in to fight day. Training volume comes down while sharpness is kept, so you arrive fresh rather than fatigued.",
  },
  gpp: {
    term: "GPP",
    definition:
      "General Physical Preparation: the base-building phase. Broad strength, conditioning and durability work that is not yet specific to your opponent or ruleset.",
  },
  spp: {
    term: "SPP",
    definition:
      "Specific Physical Preparation. Training narrows to the demands of your fight: your rounds, your positions, your pace.",
  },
};

/** The definition for a rendered label, or null when the label needs no gloss. */
export function glossaryEntry(term: string | null | undefined): GlossaryEntry | null {
  if (typeof term !== "string") {
    return null;
  }
  return GLOSSARY[term.trim().toLowerCase()] ?? null;
}
