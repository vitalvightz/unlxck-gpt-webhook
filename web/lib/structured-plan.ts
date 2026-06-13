// Pure, defensive helpers that decide how a structured_plan renders. The React
// components in components/structured-plan-renderer.tsx are thin wrappers over
// these so the rendering rules stay unit-testable (node:test) and crash-proof
// against malformed/partial payloads.
import type {
  LoadPrescription,
  MeasuredValue,
  PlanOutputs,
  StructuredBlock,
  StructuredDay,
  StructuredPlan,
  StructuredSession,
  StructuredWeek,
} from "@/lib/types";

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Trimmed non-empty string, or null. Hides null/blank/whitespace fields. */
export function cleanText(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

/** A safe array (never throws on null/non-array); empty arrays stay empty. */
export function safeArray<T>(value: T[] | null | undefined): T[] {
  return Array.isArray(value) ? value.filter((item) => item != null) : [];
}

/**
 * Whether to render the structured UI instead of the plan_text fallback.
 * True only when structured_plan is an object with at least one week. Malformed
 * or empty structures fall back to plan_text.
 */
export function shouldRenderStructuredPlan(
  outputs: Pick<PlanOutputs, "structured_plan"> | null | undefined,
): boolean {
  const plan = outputs?.structured_plan;
  if (!isObject(plan)) {
    return false;
  }
  const weeks = (plan as StructuredPlan).weeks;
  return Array.isArray(weeks) && weeks.some((week) => isObject(week));
}

const MEANINGLESS_LOAD = new Set(["", "n/a", "na", "none", "null", "-", "0", "tbd"]);

/**
 * Athlete-facing load string, or null when it should be hidden.
 * Prefers ``load.display``; hides empty/null/meaningless values.
 */
export function formatBlockLoad(load: LoadPrescription | null | undefined): string | null {
  if (!isObject(load)) {
    return null;
  }
  const display = cleanText(load.display);
  if (display && !MEANINGLESS_LOAD.has(display.toLowerCase())) {
    return display;
  }
  return null;
}

/** Rest is shown only when it carries a positive value. Hides 0-second rest. */
export function shouldShowRest(rest: MeasuredValue | null | undefined): boolean {
  return isObject(rest) && typeof rest.value === "number" && rest.value > 0;
}

/** "180 seconds" / "45 minutes" / null. */
export function formatMeasured(measured: MeasuredValue | null | undefined): string | null {
  if (!isObject(measured) || typeof measured.value !== "number") {
    return null;
  }
  const unit = cleanText(measured.unit);
  return unit ? `${measured.value} ${unit}` : `${measured.value}`;
}

/** A reps value that is really a duration string, e.g. "5-6 min", "30s", "2 min". */
export function isTimeLikeReps(reps: unknown): boolean {
  if (typeof reps !== "string") {
    return false;
  }
  return /\b(s|sec|secs|second|seconds|m|min|mins|minute|minutes|hr|hrs|hour|hours)\b/i.test(
    reps,
  ) || /\d\s*(s|m)\b/i.test(reps);
}

export type BlockMetric = { label: string; value: string };

/**
 * The single primary "how much" line for a block.
 * Prefers an explicit duration over reps when reps looks like a time string;
 * otherwise reps (with optional sets), else duration, else null.
 */
export function selectBlockMetric(block: StructuredBlock | null | undefined): BlockMetric | null {
  if (!isObject(block)) {
    return null;
  }
  const duration = formatMeasured(block.duration);
  const repsRaw = block.reps;
  const repsText =
    typeof repsRaw === "number" ? String(repsRaw) : cleanText(repsRaw as string | null);

  if ((!repsText || isTimeLikeReps(repsText)) && duration) {
    return { label: "Duration", value: duration };
  }
  if (repsText) {
    const sets = typeof block.sets === "number" && block.sets > 0 ? block.sets : null;
    return { label: "Volume", value: sets ? `${sets} × ${repsText}` : repsText };
  }
  if (duration) {
    return { label: "Duration", value: duration };
  }
  return null;
}

/** Effort like "RPE 7" / "intent: max" / null. */
export function formatEffort(block: StructuredBlock | null | undefined): string | null {
  const effort = block?.effort;
  if (!isObject(effort)) {
    return null;
  }
  const method = cleanText(effort.method);
  const value =
    typeof effort.value === "number" ? String(effort.value) : cleanText(effort.value as string);
  if (method && value) {
    return `${method} ${value}`;
  }
  return method || value || null;
}

// --- safe structural selectors (never throw on partial data) ----------------

export function getWeeks(plan: StructuredPlan | null | undefined): StructuredWeek[] {
  return safeArray(plan?.weeks).filter(isObject);
}

export function getDays(week: StructuredWeek | null | undefined): StructuredDay[] {
  return safeArray(week?.days).filter(isObject);
}

export function getSessions(day: StructuredDay | null | undefined): StructuredSession[] {
  return safeArray(day?.sessions).filter(isObject);
}

export function getBlocks(session: StructuredSession | null | undefined): StructuredBlock[] {
  return safeArray(session?.blocks).filter(isObject);
}

export function getCoachingCues(block: StructuredBlock | null | undefined): string[] {
  return safeArray(block?.coaching_cues)
    .map((cue) => cleanText(cue))
    .filter((cue): cue is string => cue !== null);
}

/** A mindset anchor only if it has at least one usable line. */
export function getMindsetLines(
  anchor: { intent?: string | null; focus_cue?: string | null; reset_cue?: string | null; confidence_anchor?: string | null } | null | undefined,
): { label: string; value: string }[] {
  if (!isObject(anchor)) {
    return [];
  }
  const lines: { label: string; value: string }[] = [];
  const intent = cleanText(anchor.intent);
  const focus = cleanText(anchor.focus_cue);
  const reset = cleanText(anchor.reset_cue);
  const confidence = cleanText(anchor.confidence_anchor);
  if (intent) lines.push({ label: "Intent", value: intent });
  if (focus) lines.push({ label: "Focus", value: focus });
  if (reset) lines.push({ label: "Reset", value: reset });
  if (confidence) lines.push({ label: "Anchor", value: confidence });
  return lines;
}

/** True when nutrition carries any displayable text. */
export function hasNutrition(plan: StructuredPlan | null | undefined): boolean {
  const nutrition = plan?.nutrition;
  if (!isObject(nutrition)) {
    return false;
  }
  return Boolean(
    cleanText(nutrition.summary) ||
      cleanText(nutrition.daily_focus) ||
      cleanText(nutrition.training_day_guidance) ||
      cleanText(nutrition.fight_week_guidance) ||
      cleanText(nutrition.weight_cut_warning?.display_text),
  );
}

/** Red-flag rules that have something to display. */
export function getDisplayableRedFlags(plan: StructuredPlan | null | undefined) {
  return safeArray(plan?.red_flag_rules)
    .filter(isObject)
    .filter((rule) => cleanText(rule.display_text));
}

export function weekLabel(week: StructuredWeek | null | undefined): string {
  const goal = cleanText(week?.week_goal);
  const index = typeof week?.week_index === "number" ? week.week_index : null;
  const base = index != null ? `Week ${index}` : "Week";
  return goal ? `${base} — ${goal}` : base;
}
