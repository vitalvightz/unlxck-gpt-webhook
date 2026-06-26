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

/** Fallback safety lines from active notes when explicit red-flag rules are absent. */
export function getFallbackSafetyNotes(plan: StructuredPlan | null | undefined): PlanNoteView[] {
  const safetyCategories = new Set(["injury", "weight_cut", "recovery"]);
  return getPlanNotes(plan).filter((note) => {
    if (shouldSuppressWeightCutSymptomEscalation(plan, note.text)) {
      return false;
    }
    if (safetyCategories.has(note.category)) {
      return true;
    }
    return /\b(stop|report|medical|coach|bleed|pain|dehydrat(?:ed|ion|e)?|wound)\b/i.test(note.text);
  });
}

/** Red-flag rules that have something to display. */
export function getDisplayableRedFlags(plan: StructuredPlan | null | undefined) {
  return safeArray(plan?.red_flag_rules)
    .filter(isObject)
    .filter((rule) => {
      const text = cleanText(rule.display_text);
      return Boolean(text && !shouldSuppressWeightCutSymptomEscalation(plan, text));
    });
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
 * as a duplicate when its normalized text contains, or is contained by, a red
 * flag's normalized display_text — this catches the common case where the note
 * is a slightly shorter paraphrase of the flag (e.g. the same escalation rule
 * minus a parenthetical). Notes shorter than the guard length are always kept.
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
const LIGHT_COMBAT_RE = /\b(light[\s-]+combat|support[\s-]+work)\b/i;
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

  if (headline) {
    let kind: SessionlessDayKind = "scheduled";
    if (LIGHT_COMBAT_RE.test(headline)) {
      kind = "light_combat";
    } else if (TECHNICAL_RE.test(headline)) {
      kind = "technical";
    } else if (SPARRING_RE.test(headline)) {
      kind = "sparring";
    } else if (COACH_LED_RE.test(headline)) {
      kind = "coach_led";
    }
    return {
      kind,
      title: headline,
      tag: SESSIONLESS_DAY_TAGS[kind],
      coachLed:
        kind === "coach_led" ||
        kind === "light_combat" ||
        kind === "sparring" ||
        kind === "technical",
    };
  }

  // No headline to classify from: fall back to a plain rest day. The converter
  // is instructed to always headline a coach-led/sparring/technical day, so a
  // headline-less session-less day is treated as genuine rest.
  return { kind: "rest", title: "Rest day", tag: null, coachLed: false };
}
