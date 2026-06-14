// Pure, defensive helpers that decide how a structured_plan renders. The React
// components in components/structured-plan-renderer.tsx are thin wrappers over
// these so the rendering rules stay unit-testable (node:test) and crash-proof
// against malformed/partial payloads.
import { formatPlanLabel, isRawEnumLabel } from "@/lib/plan-labels";
import type {
  DeterministicMacroRange,
  DeterministicNutritionPhase,
  DeterministicRecoveryPhase,
  DeterministicWeightCut,
  LoadPrescription,
  MeasuredValue,
  PlanOutputs,
  StructuredBlock,
  StructuredDay,
  StructuredPlan,
  StructuredSession,
  StructuredWeek,
} from "@/lib/types";

type MindsetLine = { label: string; value: string };

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
  return /\b(s|sec|secs|second|seconds|min|mins|minute|minutes|hr|hrs|hour|hours)\b/i.test(
    reps,
  ) || /\d\s*s\b/i.test(reps);
}

export type BlockMetric = { label: string; value: string };

/**
 * The quantitative "how much" lines for a block, in display order.
 *
 * Strength blocks use reps (with optional sets); time-based work uses duration;
 * conditioning blocks may instead (or additionally) use distance and/or rounds.
 * Prefers an explicit duration over reps when reps looks like a time string.
 * Returns an empty array when the block carries no usable metric.
 */
export function selectBlockMetric(block: StructuredBlock | null | undefined): BlockMetric[] {
  if (!isObject(block)) {
    return [];
  }
  const metrics: BlockMetric[] = [];

  const duration = formatMeasured(block.duration);
  const repsRaw = block.reps;
  const repsText =
    typeof repsRaw === "number" ? String(repsRaw) : cleanText(repsRaw as string | null);

  if ((!repsText || isTimeLikeReps(repsText)) && duration) {
    metrics.push({ label: "Duration", value: duration });
  } else if (repsText) {
    const sets = typeof block.sets === "number" && block.sets > 0 ? block.sets : null;
    metrics.push({ label: "Volume", value: sets ? `${sets} × ${repsText}` : repsText });
  } else if (duration) {
    metrics.push({ label: "Duration", value: duration });
  }

  const distance = formatMeasured(block.distance);
  if (distance) {
    metrics.push({ label: "Distance", value: distance });
  }

  if (typeof block.rounds === "number" && block.rounds > 0) {
    metrics.push({ label: "Rounds", value: String(block.rounds) });
  }

  return metrics;
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
  return getStringList(block?.coaching_cues);
}

/** A clean list of non-empty strings from a possibly-null/non-array value. */
export function getStringList(value: string[] | null | undefined): string[] {
  return safeArray(value)
    .map((item) => cleanText(item))
    .filter((item): item is string => item !== null);
}

/** A mindset anchor only if it has at least one usable line. */
export function getMindsetLines(
  anchor:
    | {
        intent?: string | null;
        focus_cue?: string | null;
        reset_cue?: string | null;
        confidence_anchor?: string | null;
        context?: string | null;
      }
    | null
    | undefined,
): { label: string; value: string }[] {
  if (!isObject(anchor)) {
    return [];
  }
  const lines: { label: string; value: string }[] = [];
  const intent = cleanText(anchor.intent);
  const focus = cleanText(anchor.focus_cue);
  const reset = cleanText(anchor.reset_cue);
  const confidence = cleanText(anchor.confidence_anchor);
  const context = cleanText(anchor.context);
  if (intent) lines.push({ label: "Intent", value: intent });
  if (focus) lines.push({ label: "Focus", value: focus });
  if (reset) lines.push({ label: "Reset", value: reset });
  if (confidence) lines.push({ label: "Anchor", value: confidence });
  if (context) lines.push({ label: "Context", value: context });
  return lines;
}

// Anchor + Context are the lower-priority mindset lines that PR-9 moves behind a
// "More" toggle to cut the card's initial vertical load. Intent/Focus/Reset stay
// visible by default. No data is dropped — only its initial visibility changes.
const SECONDARY_MINDSET_LABELS = new Set(["Anchor", "Context"]);

/** Split mindset lines into always-visible primary and collapsible secondary. */
export function splitMindsetLines(
  anchor: Parameters<typeof getMindsetLines>[0],
): { primary: MindsetLine[]; secondary: MindsetLine[] } {
  const lines = getMindsetLines(anchor);
  return {
    primary: lines.filter((line) => !SECONDARY_MINDSET_LABELS.has(line.label)),
    secondary: lines.filter((line) => SECONDARY_MINDSET_LABELS.has(line.label)),
  };
}

/**
 * The clean display view of one red-flag rule.
 *
 * ``text`` is the human-readable warning sentence (display_text). ``action`` is
 * shown only when it is a distinct human sentence — a raw enum (e.g.
 * "stop_and_report") or an action that just repeats the text is hidden so the
 * card never shows duplicated/raw machine labels. ``severityLabel`` is the
 * formatted badge (e.g. "Red").
 */
export function redFlagView(
  rule: { display_text?: string | null; action?: string | null; severity?: string | null } | null | undefined,
): { text: string | null; action: string | null; severityLabel: string | null } {
  const text = cleanText(rule?.display_text);
  const rawAction = cleanText(rule?.action);
  const action =
    rawAction && !isRawEnumLabel(rawAction) && rawAction !== text ? rawAction : null;
  const severity = cleanText(rule?.severity);
  const severityLabel = severity ? formatPlanLabel(severity) : null;
  return { text, action, severityLabel };
}

// --- deterministic (Stage 1) athlete-safe nutrition + recovery --------------

const PHASE_ORDER = ["GPP", "SPP", "TAPER", "FIGHT_WEEK", "REINTEGRATION"];

function orderedPhaseEntries<T>(byPhase: Record<string, T> | null | undefined): {
  phase: string;
  entry: T;
}[] {
  if (!isObject(byPhase)) {
    return [];
  }
  const keys = Object.keys(byPhase);
  keys.sort((a, b) => {
    const ia = PHASE_ORDER.indexOf(a.toUpperCase());
    const ib = PHASE_ORDER.indexOf(b.toUpperCase());
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  });
  return keys
    .filter((key) => isObject(byPhase[key]))
    .map((phase) => ({ phase, entry: byPhase[phase] }));
}

/** Ordered athlete-safe deterministic nutrition phases (empty when absent). */
export function getDeterministicNutritionPhases(
  plan: StructuredPlan | null | undefined,
): { phase: string; entry: DeterministicNutritionPhase }[] {
  return orderedPhaseEntries(plan?.deterministic_support?.nutrition?.by_phase);
}

/** Ordered athlete-safe deterministic recovery phases (empty when absent). */
export function getDeterministicRecoveryPhases(
  plan: StructuredPlan | null | undefined,
): { phase: string; entry: DeterministicRecoveryPhase }[] {
  return orderedPhaseEntries(plan?.deterministic_support?.recovery?.by_phase);
}

/** "112–140 g/day" / "up to 350 g/day" / "from 30 g/day" / null. */
export function formatMacroRange(
  range: DeterministicMacroRange | null | undefined,
  unit: string,
): string | null {
  if (!isObject(range)) {
    return null;
  }
  const min = typeof range.min === "number" ? range.min : null;
  const max = typeof range.max === "number" ? range.max : null;
  if (min != null && max != null) {
    return `${min}–${max} ${unit}`;
  }
  if (max != null) {
    return `up to ${max} ${unit}`;
  }
  if (min != null) {
    return `from ${min} ${unit}`;
  }
  return null;
}

/** A macro line combining its numeric range and any deterministic note. */
export function macroLine(
  range: DeterministicMacroRange | null | undefined,
  unit: string,
): string | null {
  const numeric = formatMacroRange(range, unit);
  const note = cleanText(range?.note);
  if (numeric && note) return `${numeric} (${note})`;
  return numeric || note || null;
}

/** Athlete-safe weight-cut summary (risk band + supervision) — never dosing. */
export function formatWeightCutBand(
  weightCut: DeterministicWeightCut | null | undefined,
): { band: string; supervisionRequired: boolean } | null {
  if (!isObject(weightCut)) {
    return null;
  }
  const band = cleanText(weightCut.risk_band);
  if (!band || band.toLowerCase() === "none") {
    return null;
  }
  return { band, supervisionRequired: weightCut.supervision_required === true };
}

/** The athlete-safe metric rows for one deterministic nutrition phase. */
export function nutritionPhaseRows(
  entry: DeterministicNutritionPhase | null | undefined,
): { label: string; value: string }[] {
  if (!isObject(entry)) {
    return [];
  }
  const rows: { label: string; value: string }[] = [];
  const push = (label: string, value: string | null) => {
    if (value) rows.push({ label, value });
  };
  push("Protein", macroLine(entry.protein_g_per_day, "g/day"));
  push("Carbs", macroLine(entry.carbs_g_per_day, "g/day"));
  push("Fats", macroLine(entry.fats_g_per_day, "g/day"));
  push("Hydration", macroLine(entry.hydration_ml_per_day, "ml/day"));
  push("Meals", cleanText(entry.meal_structure));
  const fuel = entry.fuel_timing;
  if (isObject(fuel)) {
    push("Fuel — pre", cleanText(fuel.pre));
    push("Fuel — intra", cleanText(fuel.intra));
    push("Fuel — post", cleanText(fuel.post));
  }
  const fatigue = cleanText(entry.fatigue_adjustment);
  if (fatigue) push("Fatigue adjustment", `${fatigue} fatigue support`);
  return rows;
}

/** The athlete-safe recovery view for one deterministic recovery phase. */
export function recoveryPhaseView(entry: DeterministicRecoveryPhase | null | undefined): {
  sleep: string | null;
  coreStrategies: string[];
  phaseFocus: string[];
  fatigue: string[];
  ageAdjustments: string[];
  weightCut: { band: string; supervisionRequired: boolean } | null;
} {
  const e = isObject(entry) ? entry : {};
  const sleepRange = safeArray(e.sleep_hours_target).filter(
    (n): n is number => typeof n === "number",
  );
  const sleep =
    sleepRange.length === 2
      ? `${sleepRange[0]}–${sleepRange[1]} h/night`
      : sleepRange.length === 1
        ? `${sleepRange[0]} h/night`
        : null;
  return {
    sleep,
    coreStrategies: getStringList(e.core_strategies),
    phaseFocus: getStringList(e.phase_focus),
    // fatigue_flags (high) or fatigue_notes (moderate) — whichever is present.
    fatigue: getStringList(e.fatigue_flags).concat(getStringList(e.fatigue_notes)),
    ageAdjustments: getStringList(e.age_adjustments),
    weightCut: formatWeightCutBand(e.weight_cut),
  };
}

/** True when the plan carries deterministic athlete-safe nutrition data. */
export function hasDeterministicNutrition(plan: StructuredPlan | null | undefined): boolean {
  return getDeterministicNutritionPhases(plan).some(
    ({ entry }) =>
      nutritionPhaseRows(entry).length > 0 || formatWeightCutBand(entry.weight_cut) !== null,
  );
}

/** True when the plan carries deterministic athlete-safe recovery data. */
export function hasDeterministicRecovery(plan: StructuredPlan | null | undefined): boolean {
  return getDeterministicRecoveryPhases(plan).some(({ entry }) => {
    const view = recoveryPhaseView(entry);
    return (
      view.sleep !== null ||
      view.coreStrategies.length > 0 ||
      view.phaseFocus.length > 0 ||
      view.fatigue.length > 0 ||
      view.ageAdjustments.length > 0 ||
      view.weightCut !== null
    );
  });
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
