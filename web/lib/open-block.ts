// The renewable open-plan development block: Week 1 baseline, Week 2 small
// progression, Week 3 highest controlled, Week 4 deload/reassess (mirrors
// open_plan_spec.development_block in fightcamp/stage2_payload_open_ongoing.py).
//
// An open plan's four weeks share one weekly rhythm, so without this overlay
// they render as identical clones and the block's built-in wave never reaches
// the athlete. These helpers turn the week position into the athlete-facing
// intent (week strip / week overview / Today) and into a per-exercise
// directive on each block card. Display-level only: doses are never mutated,
// so a future Stage 2 payload that emits explicit per-week doses simply
// replaces the fallback wording here.

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
 * own progression rule (or a safe generic bump when the block has none, or
 * only a stop rule); the deload week always overrides with a volume cut.
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
    return {
      label: "This week",
      text:
        rule ??
        "Add one set or a small load bump, only if last week felt controlled.",
      usesProgressionRule: rule !== null,
    };
  }
  if (intent.key === "deload") {
    return {
      label: "This week",
      text: "Deload — cut working sets roughly in half, keep loads light, and stop fresh.",
      usesProgressionRule: false,
    };
  }
  return null;
}
