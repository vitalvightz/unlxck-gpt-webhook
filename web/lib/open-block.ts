// The renewable open-plan development block: Week 1 baseline, Week 2 small
// progression, Week 3 highest controlled, Week 4 deload/reassess (mirrors
// open_plan_spec.development_block in fightcamp/stage2_payload_open_ongoing.py).
//
// An open plan's four weeks share one weekly rhythm, so without this overlay
// they render as identical clones and the block's built-in wave never reaches
// the athlete. These helpers turn the week position into the athlete-facing
// intent (week strip / week overview / Today) and into a per-exercise
// directive on each block card. Display-level only: doses are never mutated
// and no wording is invented here — the per-block progression/deload text is
// written by the structured-card conversion, which knows the exercise type.

import { cleanText, progressionRuleLabel } from "@/lib/structured-plan";
import type { StructuredBlock } from "@/lib/types";

export type OpenBlockWeekKey = "baseline" | "progress" | "peak" | "deload";

export type OpenBlockWeekIntent = {
  key: OpenBlockWeekKey;
  /** 1-based week number inside the renewable block. */
  weekNumber: number;
  /** Short label shown on the week pill. */
  label: string;
  /** One-line week policy shown in the week overview and on Today. */
  summary: string;
};

const OPEN_BLOCK_WEEK_INTENTS: readonly OpenBlockWeekIntent[] = [
  {
    key: "baseline",
    weekNumber: 1,
    label: "Baseline",
    summary: "Run every dose as written and groove technical consistency.",
  },
  {
    key: "progress",
    weekNumber: 2,
    label: "Progress",
    summary:
      "Small progression — apply each exercise's progression rule, but only where last week felt controlled.",
  },
  {
    key: "peak",
    weekNumber: 3,
    label: "Highest controlled",
    summary:
      "The block's top week — progress again only while movement quality holds.",
  },
  {
    key: "deload",
    weekNumber: 4,
    label: "Deload + reassess",
    summary:
      "Cut working volume roughly in half, stop every session fresh, and reassess for the next block.",
  },
];

/** Pill labels for the open-plan week strip, in block order. */
export const OPEN_BLOCK_WEEK_LABELS: readonly string[] = OPEN_BLOCK_WEEK_INTENTS.map(
  (intent) => intent.label,
);

/** The development-block intent for a 1-based week number, or null outside the
 * four-week block (callers gate on the plan being open/ongoing). */
export function openBlockWeekIntent(
  weekNumber: number | null | undefined,
): OpenBlockWeekIntent | null {
  if (typeof weekNumber !== "number" || !Number.isFinite(weekNumber)) {
    return null;
  }
  return OPEN_BLOCK_WEEK_INTENTS[Math.trunc(weekNumber) - 1] ?? null;
}

export type OpenBlockWeekDirective = {
  /** Aside label on the block card. */
  label: string;
  text: string;
  /** True when the text IS the block's own progression rule, so the generic
   * progression aside would duplicate it and should be suppressed. */
  usesProgressionRule: boolean;
};

/** True when the block carries a genuine progression rule (not a stop rule). */
function progressionRuleText(block: StructuredBlock): string | null {
  const rule = cleanText(block.progression_rule);
  if (!rule || progressionRuleLabel(rule) !== "Progress") {
    return null;
  }
  return rule;
}

/**
 * The week-directed instruction for one block card. Baseline weeks return null
 * (the dose is already the instruction); progression weeks surface the block's
 * own progression rule and the deload week its own deload rule, both written
 * per exercise by the structured-card conversion.
 *
 * A block with no such rule returns null rather than a generic directive: the
 * old "add one set or a small load bump" / "cut working sets roughly in half"
 * fallbacks were invented here, so they told an easy aerobic ride, a mobility
 * drill or a rehab insert to do something that does not apply to it. The week
 * intent still carries the block-level policy for the week strip and overview.
 */
export function openBlockWeekDirective(
  intent: OpenBlockWeekIntent | null | undefined,
  block: StructuredBlock,
): OpenBlockWeekDirective | null {
  if (!intent) {
    return null;
  }
  if (intent.key === "progress" || intent.key === "peak") {
    const rule = progressionRuleText(block);
    if (!rule) {
      return null;
    }
    return { label: "This week", text: rule, usesProgressionRule: true };
  }
  if (intent.key === "deload") {
    const deload = cleanText(block.deload_rule);
    if (!deload) {
      return null;
    }
    return { label: "This week", text: deload, usesProgressionRule: false };
  }
  return null;
}
