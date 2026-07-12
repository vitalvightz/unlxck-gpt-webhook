// Pure, defensive helpers that decide how a structured_plan renders. The React
// components in components/structured-plan-renderer.tsx are thin wrappers over
// these so the rendering rules stay unit-testable (node:test) and crash-proof
// against malformed/partial payloads.
import { formatPlanLabel, isRawEnumLabel } from "./plan-labels.ts";
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

/** "180 seconds" / "45 minutes" / null. Rejects non-finite (NaN/Infinity) and
 * negative values — a duration/rest/distance/work measure is never below zero,
 * and a bad number must not leak into the card as "NaN seconds". */
export function formatMeasured(measured: MeasuredValue | null | undefined): string | null {
  if (
    !isObject(measured) ||
    typeof measured.value !== "number" ||
    !Number.isFinite(measured.value) ||
    measured.value < 0
  ) {
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

  const sets = typeof block.sets === "number" && block.sets > 0 ? block.sets : null;
  if ((!repsText || isTimeLikeReps(repsText)) && duration) {
    metrics.push({ label: "Duration", value: duration });
  } else if (repsText && isTimeLikeReps(repsText)) {
    // The reps value is itself a duration ("30 seconds") and no separate
    // duration exists, so it is time, not a rep count — labelling it "Volume"
    // ("5 × 30 seconds") is semantically wrong. Surface it as Duration, keeping
    // any sets multiplier for the interval count.
    metrics.push({ label: "Duration", value: sets ? `${sets} × ${repsText}` : repsText });
  } else if (repsText) {
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

/** Local ISO date (YYYY-MM-DD) for the Monday of the week containing `dateStr`. */
function calendarWeekMonday(dateStr: string | null): string | null {
  if (!dateStr) {
    return null;
  }
  const parsed = new Date(`${dateStr.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  // getDay(): 0=Sun..6=Sat -> offset back to Monday (0=Mon..6=Sun).
  const offsetToMonday = (parsed.getDay() + 6) % 7;
  parsed.setDate(parsed.getDate() - offsetToMonday);
  const y = parsed.getFullYear();
  const m = String(parsed.getMonth() + 1).padStart(2, "0");
  const d = String(parsed.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** Whole days between two local ISO date strings, or null if either is unusable. */
function daySpan(startIso: string, endIso: string): number | null {
  const start = new Date(`${startIso.slice(0, 10)}T00:00:00`);
  const end = new Date(`${endIso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
    return null;
  }
  return Math.round((end.getTime() - start.getTime()) / 86_400_000);
}

/**
 * Split one plan week into per-calendar-week (Mon–Sun) display weeks.
 *
 * Normal camp weeks already fit inside a single calendar week, so they pass
 * through unchanged. A late-fight / bridge plan, however, ships its whole
 * countdown as ONE week object spanning two or three calendar weeks — which the
 * UI would otherwise render as a single "Week 1" listing every day. Splitting it
 * on Monday boundaries restores the week-by-week view. Each sub-week inherits the
 * source week's metadata but gets its own day list and recomputed date/countdown
 * range. Days without a parseable date stay with the preceding sub-week.
 *
 * Guarded to only ever touch a genuinely long block: a week whose dated days
 * span 7 days or fewer is returned untouched even if it happens to cross a
 * Monday, so a normally-structured camp week is never re-cut.
 */
function splitWeekByCalendarWeek(week: StructuredWeek): StructuredWeek[] {
  const days = getDays(week);
  const datedSorted = days
    .map((day) => cleanText(day.date))
    .filter((value): value is string => value !== null)
    .sort();
  if (datedSorted.length > 0) {
    const span = daySpan(datedSorted[0], datedSorted[datedSorted.length - 1]);
    if (span === null || span <= 7) {
      return [week];
    }
  }

  const groups: { monday: string; days: StructuredDay[] }[] = [];
  const leadingUndated: StructuredDay[] = [];

  for (const day of days) {
    const monday = calendarWeekMonday(cleanText(day.date));
    if (monday === null) {
      if (groups.length > 0) {
        groups[groups.length - 1].days.push(day);
      } else {
        leadingUndated.push(day);
      }
      continue;
    }
    const existing = groups.find((group) => group.monday === monday);
    if (existing) {
      existing.days.push(day);
    } else {
      groups.push({ monday, days: [day] });
    }
  }

  // One calendar week (or no dates to split on) -> leave the week untouched.
  if (groups.length <= 1) {
    return [week];
  }

  groups.sort((a, b) => (a.monday < b.monday ? -1 : a.monday > b.monday ? 1 : 0));
  if (leadingUndated.length > 0) {
    groups[0].days = [...leadingUndated, ...groups[0].days];
  }

  return groups.map((group, index) => {
    const dates = group.days
      .map((day) => cleanText(day.date))
      .filter((value): value is string => value !== null)
      .sort();
    const labels = group.days
      .map((day) => cleanText(day.countdown_label))
      .filter((value): value is string => value !== null);
    return {
      ...week,
      week_id: `${cleanText(week.week_id) || "week"}-${group.monday}-cw${index + 1}`,

      days: group.days,
      start_date: dates[0] ?? week.start_date,
      end_date: dates[dates.length - 1] ?? week.end_date,
      // Days run furthest-from-fight first, so the first/last labels bound the range.
      countdown_start: labels[0] ?? week.countdown_start,
      countdown_end: labels[labels.length - 1] ?? week.countdown_end,
    };
  });
}

export function getWeeks(plan: StructuredPlan | null | undefined): StructuredWeek[] {
  const raw = safeArray(plan?.weeks).filter(isObject);
  const split = raw.flatMap(splitWeekByCalendarWeek);
  // No week spanned multiple calendar weeks -> identity (zero change for normal
  // camps). Only when a split happened do we renumber week_index so the strip
  // reads Week 1, 2, 3… in order.
  if (split.length === raw.length) {
    return raw;
  }
  return split.map((week, index) => ({ ...week, week_index: index + 1 }));
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

const REHAB_BLOCK_RE = /\b(rehab|prehab|mobility|mobil(?:ity|isation|ization)|isometric|opener)\b/i;

/** Rehab/mobility blocks get a compact always-visible summary on session cards. */
export function isRehabOrMobilityBlock(block: StructuredBlock | null | undefined): boolean {
  if (!isObject(block)) {
    return false;
  }
  return [block.block_type, block.category, block.display_name]
    .map((value) => cleanText(value))
    .some((value) => Boolean(value && REHAB_BLOCK_RE.test(value)));
}

/** Ordered rehab/mobility blocks for a session, empty when absent. */
export function getRehabOrMobilityBlocks(
  session: StructuredSession | null | undefined,
): StructuredBlock[] {
  return getBlocks(session).filter(isRehabOrMobilityBlock);
}

export function getCoachingCues(block: StructuredBlock | null | undefined): string[] {
  return getStringList(block?.coaching_cues);
}

// A stop rule reads like "Stop on sharp pain." / "Stop the set if punch speed
// drops" / "stop if the ankle flares". The conversion model frequently drops
// these into a block's `progression_rule` (its only free-text "what to do"
// field), so the renderer must not label a stop rule as "Progress" — that told
// the athlete to ADVANCE on a safety cue. Detect the stop-rule shape so it can
// be labelled correctly.
const STOP_RULE_RE = /^\s*stop(?!-)\b|(?<!\bdo\snot\s|don't\s|never\s)(?<!-)\bstop (?:the set|on|if|when|immediately)\b/i;

/** Whether a `progression_rule` string is really a stop/safety rule. */
export function isStopRuleText(text: string | null | undefined): boolean {
  const clean = cleanText(text);
  return clean !== null && STOP_RULE_RE.test(clean);
}

/** The label a block's `progression_rule` should render under: a stop rule is
 * surfaced as "Stop rule", genuine progression stays "Progress". */
export function progressionRuleLabel(text: string | null | undefined): "Progress" | "Stop rule" {
  return isStopRuleText(text) ? "Stop rule" : "Progress";
}

/** A clean list of non-empty strings from a possibly-null/non-array value. */
export function getStringList(value: string[] | null | undefined): string[] {
  return safeArray(value)
    .map((item) => cleanText(item))
    .filter((item): item is string => item !== null);
}

/** A simplified mindset anchor only if it has at least one usable line. */
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
  const context = cleanText(anchor.context);
  if (intent) lines.push({ label: "Intent", value: intent });
  if (focus) lines.push({ label: "Focus", value: focus });
  if (context) lines.push({ label: "Context", value: context });
  return lines;
}

export function splitMindsetLines(
  anchor: Parameters<typeof getMindsetLines>[0],
): { primary: MindsetLine[]; secondary: MindsetLine[] } {
  const lines = getMindsetLines(anchor);
  return {
    primary: lines,
    secondary: [],
  };
}

export function redFlagView(
  rule:
    | { display_text?: string | null; action?: string | null; severity?: string | null }
    | null
    | undefined,
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

/** Stable key used to attach deterministic support to matching week phases. */
export function normalizeSupportPhaseKey(value: unknown): string | null {
  const token = cleanText(value)
    ?.toLowerCase()
    .replace(/[\s\-/]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "");
  if (!token) {
    return null;
  }
  if (token === "gpp" || token.includes("general_prep") || token.includes("general_preparation")) {
    return "gpp";
  }
  if (token === "spp" || token.includes("specific_prep") || token.includes("specific_preparation")) {
    return "spp";
  }
  if (token === "taper") {
    return "taper";
  }
  if (token.includes("fight_week") || token.includes("fight_week_taper")) {
    return "fight_week";
  }
  if (token.includes("reintegration")) {
    return "reintegration";
  }
  return token;
}

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

const WEIGHT_CUT_RISK_RANK: Record<string, number> = {
  none: 0,
  inactive: 0,
  low: 1,
  mild: 1,
  moderate: 2,
  medium: 2,
  amber: 2,
  elevated: 2,
  high: 3,
  severe: 3,
  red: 3,
  critical: 4,
  extreme: 4,
  aggressive: 4,
};

function weightCutRiskRank(value: unknown): number {
  const token = cleanText(value)?.toLowerCase().replace(/[\s-]+/g, "_");
  if (!token) {
    return 0;
  }
  if (WEIGHT_CUT_RISK_RANK[token] != null) {
    return WEIGHT_CUT_RISK_RANK[token];
  }
  return Math.max(
    ...Object.entries(WEIGHT_CUT_RISK_RANK)
      .filter(([key]) => token.includes(key))
      .map(([, rank]) => rank),
    0,
  );
}

function maxWeightCutRiskRank(plan: StructuredPlan | null | undefined): number {
  const ranks = [weightCutRiskRank(plan?.nutrition?.weight_cut_warning?.risk_level)];
  for (const { entry } of getDeterministicNutritionPhases(plan)) {
    ranks.push(weightCutRiskRank(entry.weight_cut?.risk_band));
  }
  for (const { entry } of getDeterministicRecoveryPhases(plan)) {
    ranks.push(weightCutRiskRank(entry.weight_cut?.risk_band));
  }
  return Math.max(...ranks, 0);
}

function hasWeightCutRiskAboveModerate(plan: StructuredPlan | null | undefined): boolean {
  return maxWeightCutRiskRank(plan) > WEIGHT_CUT_RISK_RANK.moderate;
}

function isWeightCutSymptomEscalationText(text: string): boolean {
  const normalized = text.toLowerCase();
  return (
    /\bweight[-\s]?cut\b/.test(normalized) &&
    (
      /\bsymptoms?\s+worsen\b/.test(normalized) ||
      /\bworsen(?:s|ed|ing)?\b/.test(normalized) ||
      /\blightheaded(?:ness)?\b/.test(normalized) ||
      /\bdizz(?:y|iness)\b/.test(normalized) ||
      /\bdehydrat(?:ed|ion|e)?\b/.test(normalized)
    )
  );
}

function shouldSuppressWeightCutSymptomEscalation(
  plan: StructuredPlan | null | undefined,
  text: string,
): boolean {
  return isWeightCutSymptomEscalationText(text) && !hasWeightCutRiskAboveModerate(plan);
}

/**
 * Whether a weight-cut symptom safety line should be visually DE-EMPHASISED —
 * shown, but softened — because the athlete's computed cut risk is below
 * moderate. It is never suppressed: a symptom-based stop/escalate rule ("if you
 * feel dizzy/dehydrated, stop and report") is generically safe advice, and a
 * predicted risk band does not make actual symptoms unimportant. Below moderate
 * risk we only tone it down so it does not lead the card; at/above moderate it
 * renders at full weight. Used by the renderer to pick the softer style.
 */
export function isDeEmphasisedWeightCutSafety(
  plan: StructuredPlan | null | undefined,
  text: string | null | undefined,
): boolean {
  const clean = cleanText(text);
  return clean !== null && isWeightCutSymptomEscalationText(clean) && !hasWeightCutRiskAboveModerate(plan);
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

export type PlanNoteView = { category: string; label: string | null; text: string };

const PLAN_NOTE_CATEGORY_LABELS: Record<string, string> = {
  weight_cut: "Weight cut",
  injury: "Injury",
  nutrition: "Nutrition",
  training: "Training",
  recovery: "Recovery",
  general: "Note",
};

/** Short title for a plan note: its own label, else a category fallback. */
export function planNoteLabel(note: PlanNoteView): string {
  if (note.label) {
    return note.label;
  }
  return PLAN_NOTE_CATEGORY_LABELS[note.category] ?? PLAN_NOTE_CATEGORY_LABELS.general;
}

/** Plan-level "active notes" that carry displayable text (empty when absent). */
export function getPlanNotes(plan: StructuredPlan | null | undefined): PlanNoteView[] {
  return safeArray(plan?.plan_notes)
    .filter(isObject)
    .map((note) => {
      const text = cleanText(note.text);
      if (!text) {
        return null;
      }
      const category = cleanText(note.category)?.toLowerCase().replace(/[-\s]+/g, "_") ?? "general";
      return { category, label: cleanText(note.label), text } satisfies PlanNoteView;
    })
    .filter((note): note is PlanNoteView => note !== null);
}

/** Fallback safety lines from active notes when explicit red-flag rules are
 * absent. A weight-cut symptom safety line is ALWAYS surfaced here (it is a
 * stop/escalate rule); the renderer de-emphasises it below moderate risk rather
 * than hiding it. */
export function getFallbackSafetyNotes(plan: StructuredPlan | null | undefined): PlanNoteView[] {
  const safetyCategories = new Set(["injury", "weight_cut", "recovery"]);
  return getPlanNotes(plan).filter((note) => {
    if (safetyCategories.has(note.category)) {
      return true;
    }
    return /\b(stop|report|medical|coach|bleed|pain|dehydrat(?:ed|ion|e)?|wound)\b/i.test(note.text);
  });
}

/** Red-flag rules that have something to display. Explicit symptom-based safety
 * rules (incl. weight-cut symptom escalation) are never suppressed by risk band
 * — they always render; the renderer softens the below-moderate ones. */
export function getDisplayableRedFlags(plan: StructuredPlan | null | undefined) {
  return safeArray(plan?.red_flag_rules)
    .filter(isObject)
    .filter((rule) => Boolean(cleanText(rule.display_text)));
}

/** Loose normalization for de-duplicating a note against a red-flag rule:
 *  lowercased, parentheticals dropped, all punctuation/whitespace collapsed to
 *  single spaces. Lets "…worsen, stop…" match "…worsen (lightheadedness), stop…". */
function normalizeForDup(text: string): string {
  return text
    .toLowerCase()
    .replace(/\([^)]*\)/g, " ")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

/**
 * Active notes with any note that merely restates a red-flag rule removed, so
 * the Red Flags card stays the single home for stop/report rules. A note counts
 * as a duplicate only on EXACT normalized equality with a red flag's normalized
 * display_text. Substring ("contains / is contained by") matching is
 * deliberately NOT used here: these are safety notes, and a looser match risks
 * hiding a note that merely shares wording with a flag but adds its own
 * instruction. Over-suppressing safety copy is the more dangerous failure, so we
 * keep the stricter equality check. Notes shorter than the guard length are
 * always kept. The ``normalizeForDup`` helper still absorbs the common
 * parenthetical-only difference, which is the case this dedup targets.
 */
export function getActiveNotesExcludingRedFlags(
  plan: StructuredPlan | null | undefined,
): PlanNoteView[] {
  const notes = getPlanNotes(plan).filter(
    (note) => !shouldSuppressWeightCutSymptomEscalation(plan, note.text),
  );
  const flagTexts = getDisplayableRedFlags(plan)
    .map((rule) => cleanText(rule.display_text))
    .filter((text): text is string => text !== null)
    .map(normalizeForDup)
    .filter((text) => text.length >= 12);
  if (flagTexts.length === 0) {
    return notes;
  }
  return notes.filter((note) => {
    const noteNorm = normalizeForDup(note.text);
    if (noteNorm.length < 12) {
      return true;
    }
    return !flagTexts.some((flag) => flag === noteNorm);
  });
}

// The week heading must read as a glanceable label, not a paragraph. The LLM is
// told to keep week_goal to ~6 words, but plans (and older saved plans) can still
// carry a full multi-clause sentence, so we shorten deterministically: keep the
// first clause (up to the first ; or .) when that already fits in 6 words, else
// hard-cap at 6 words with an ellipsis. Goals already short are returned verbatim
// so their punctuation (e.g. a trailing period) is preserved.
const WEEK_GOAL_MAX_WORDS = 6;
function shortenWeekGoal(goal: string): string {
  const words = goal.split(/\s+/).filter(Boolean);
  if (words.length <= WEEK_GOAL_MAX_WORDS) {
    return goal;
  }
  const firstClause = goal.split(/[;.](?=\\s|$)/)[0].trim();
  const clauseWords = firstClause.split(/\s+/).filter(Boolean);
  if (clauseWords.length > 0 && clauseWords.length <= WEEK_GOAL_MAX_WORDS) {
    return firstClause;
  }
  return `${words.slice(0, WEEK_GOAL_MAX_WORDS).join(" ")}…`;
}

export function weekLabel(week: StructuredWeek | null | undefined): string {
  const goal = cleanText(week?.week_goal);
  const index = typeof week?.week_index === "number" ? week.week_index : null;
  const base = index != null ? `Week ${index}` : "Week";
  return goal ? `${base} — ${shortenWeekGoal(goal)}` : base;
}

// --- session-less day classification ----------------------------------------
//
// A coach-led / sparring / technical day legitimately carries no app S&C
// blocks (the contact load is owned by the coach), so the converter emits it as
// a day with an empty `sessions` array. Rather than relying on the LLM to build
// a session object for these — which wastes tokens and is a frequent source of
// dropped days — we deterministically derive a self-contained card from the
// day's own `today_card.headline` + `day_type`. Only a genuine rest/recovery
// day (or a truly empty day) falls through to "Rest day.".

const REST_DAY_TYPES = new Set(["rest", "recovery"]);
// `technical` is checked before `sparring` so a "technical only / no hard
// sparring" headline is not mislabelled as a sparring day by the stray
// "sparring" token, and `coach_led` is the catch-all for coach-owned contact.
const LIGHT_COMBAT_RE = /\b(light(?:[\s-]+technical)?[\s-]+combat|support[\s-]+work)\b/i;
const TECHNICAL_RE = /\b(technical|skill|drill|pad\s?work|pads|mitts?|footwork|shadow)/i;
const SPARRING_RE = /\bspar(?:r(?:ing|ed)|s)?\b/i;
const COACH_LED_RE = /\bcoach/i;

export type SessionlessDayKind =
  | "coach_led"
  | "light_combat"
  | "sparring"
  | "technical"
  | "scheduled"
  | "rest";

export type SessionlessDayView = {
  kind: SessionlessDayKind;
  title: string;
  /** Short tag for the day kind, or null when no kind tag should show. */
  tag: string | null;
  /** Whether to surface the "no app S&C — train with your coach" note. */
  coachLed: boolean;
};

const SESSIONLESS_DAY_TAGS: Record<SessionlessDayKind, string | null> = {
  coach_led: "Coach-led",
  light_combat: "Light combat",
  sparring: "Sparring",
  technical: "Technical",
  scheduled: null,
  rest: null,
};

/** The day kind for a coach-led/contact headline (scheduled when none matches). */
function coachLedKindFromHeadline(headline: string): SessionlessDayKind {
  if (LIGHT_COMBAT_RE.test(headline)) {
    return "light_combat";
  }
  if (TECHNICAL_RE.test(headline)) {
    return "technical";
  }
  if (SPARRING_RE.test(headline)) {
    return "sparring";
  }
  if (COACH_LED_RE.test(headline)) {
    return "coach_led";
  }
  return "scheduled";
}

/**
 * Deterministically resolve how a day with no app sessions should render.
 *
 * Coach-led/sparring/technical days get their own card titled from the day
 * headline so a mostly-coach-led camp does not collapse into a wall of
 * "Rest day.". A headline-less rest/recovery day (or an otherwise empty day)
 * is the only case that renders as a rest day.
 */
export function classifySessionlessDay(
  day: StructuredDay | null | undefined,
): SessionlessDayView {
  const headline = cleanText(day?.today_card?.headline);
  const dayType = cleanText(day?.day_type)?.toLowerCase() ?? null;

  if (headline) {
    const kind = coachLedKindFromHeadline(headline);
    // A rest/recovery day_type whose headline does not clearly identify
    // coach-led combat / sparring / technical work stays a rest day (e.g.
    // day_type "rest" + "Full rest and mobility"), rather than a generic
    // "scheduled" day. day_type is only allowed to override an unclassified
    // headline — a headline that names real combat/coach work always wins.
    if (kind === "scheduled" && dayType !== null && REST_DAY_TYPES.has(dayType)) {
      return { kind: "rest", title: headline, tag: null, coachLed: false };
    }
    return {
      kind,
      title: headline,
      tag: SESSIONLESS_DAY_TAGS[kind],
      coachLed:
        kind === "coach_led" ||
        kind === "sparring" ||
        kind === "technical",
    };
  }

  // No headline to classify from: fall back to a plain rest day. The converter
  // is instructed to always headline a coach-led/sparring/technical day, so a
  // headline-less session-less day is treated as genuine rest.
  return { kind: "rest", title: "Rest day", tag: null, coachLed: false };
}

export type CoachLedContactView = {
  kind: SessionlessDayKind;
  title: string;
  tag: string | null;
};

/**
 * Coach-owned contact (declared / downgraded sparring) that coexists with a
 * day's app sessions, or null when none is set. Driven by the deterministic
 * ``today_card.coach_led_contact`` field rather than the day headline (which a
 * session day uses for its own session title), so surfacing the contact never
 * clobbers the app session. The renderer shows it as a context block above the
 * session cards.
 */
export function getCoachLedContactView(
  day: StructuredDay | null | undefined,
): CoachLedContactView | null {
  const headline = cleanText(day?.today_card?.coach_led_contact);
  if (!headline) {
    return null;
  }
  const kind = coachLedKindFromHeadline(headline);
  return { kind, title: headline, tag: SESSIONLESS_DAY_TAGS[kind] };
}
