import type { BlockMetric } from "./structured-plan";

function clean(value: string | null | undefined): string {
  return (value || "").trim();
}

function normalize(value: string): string {
  return value.toLowerCase().replace(/\s+/g, " ").replace(/[.\s]+$/, "").trim();
}

function stripStopLabel(value: string): string {
  return clean(value).replace(/^stop(?:\s+rule)?\s*:\s*/i, "").trim();
}

function safetyConcepts(value: string): Set<string> {
  const text = normalize(value);
  const concepts = new Set<string>();
  if (/\bpain\b/.test(text)) concepts.add("pain");
  if (/\b(?:wound|abrasion|graze|skin|cut|irritat\w*|cover\w*|bleed\w*|redness|infect\w*|drainage)\b/.test(text)) {
    concepts.add("surface");
  }
  if (/\bswell\w*\b/.test(text)) concepts.add("swelling");
  if (/\b(?:numb\w*|tingl\w*|weakness|giving way|instability)\b/.test(text)) concepts.add("neuro");
  return concepts;
}

function globalConcepts(values: readonly string[]): Set<string> {
  const result = new Set<string>();
  for (const value of values) {
    for (const concept of safetyConcepts(value)) result.add(concept);
  }
  return result;
}

function isOwnedSafetyClause(value: string, owned: Set<string>): boolean {
  const concepts = safetyConcepts(value);
  return concepts.size > 0 && [...concepts].every((concept) => owned.has(concept));
}

function splitStopClauses(value: string): string[] {
  return value
    .split(/\s*;\s*|,\s*(?:or\s+)?|\s+or\s+/i)
    .map((part) => part.replace(/^\s*(?:or\s+)?(?:if\s+)?/i, "").trim())
    .filter(Boolean);
}

/**
 * One exercise owns at most one athlete-facing stop rule. Plan-level injury and
 * red-flag copy owns global safety; the exercise keeps the first remaining
 * block-specific quality/form criterion. Already-saved plans are handled here
 * at display time without mutating stored rows.
 */
export function selectCompactStopRule(
  stopRules: readonly string[],
  planSafetyTexts: readonly string[] = [],
): string | null {
  const rules = stopRules.map(stripStopLabel).filter(Boolean);
  if (rules.length === 0) return null;
  const owned = globalConcepts(planSafetyTexts);
  if (owned.size === 0) return rules[0];

  for (const rule of rules) {
    if (!isOwnedSafetyClause(rule, owned)) return rule;
    for (const clause of splitStopClauses(rule)) {
      if (!isOwnedSafetyClause(clause, owned)) return clause;
    }
  }
  return null;
}

const ESCALATION_ACTION_RE =
  /\b(?:stop|seek\s+(?:medical\s+)?care|report|medical\s+review|urgent|do\s+not\s+train|no\s+contact)\b/i;

/** Active Notes owns context/management, not escalation already owned by Safety Priority. */
export function stripSafetyOwnedClause(
  text: string,
  safetyPriorityTexts: readonly string[],
): string {
  const original = clean(text);
  if (!original || safetyPriorityTexts.length === 0) return original;
  const owned = globalConcepts(safetyPriorityTexts);
  if (owned.size === 0) return original;

  const kept = original
    .split(/(?<=[.!?])\s+|\s*;\s*/)
    .map((part) => part.trim())
    .filter(
      (part) =>
        part && !(ESCALATION_ACTION_RE.test(part) && isOwnedSafetyClause(part, owned)),
    );
  return kept.join(" ").trim();
}

function countdownSection(source: string, countdown: string | null | undefined): string {
  const target = clean(countdown).toUpperCase();
  if (!target) return source;
  const lines = source.split(/\r?\n/);
  const selected: string[] = [];
  let inTarget = false;
  for (const line of lines) {
    const heading = line.match(/^\s*(?:#{1,6}\s*)?(D-\d+)\b/i);
    if (heading) {
      const label = heading[1].toUpperCase();
      if (inTarget && label !== target) break;
      inTarget = label === target;
    }
    if (inTarget) selected.push(line);
  }
  return selected.length > 0 ? selected.join("\n") : source;
}

function sourceBlockLine(
  source: string | null | undefined,
  blockName: string,
  countdown: string | null | undefined,
): string | null {
  const raw = clean(source);
  const name = normalize(blockName);
  if (!raw || !name) return null;
  const scoped = countdownSection(raw, countdown);
  const find = (text: string) =>
    text
      .split(/\r?\n/)
      .find((line) => normalize(line).includes(name) && /\b(?:sets?|rpe|rir)\b/i.test(line)) || null;
  return find(scoped) || (scoped === raw ? null : find(raw));
}

export type SourcePrescriptionRangeOverrides = {
  sets: string | null;
  effort: string | null;
};

/**
 * Recover only explicit numeric RANGES from the authoritative original plan.
 * This is deliberately narrow: no scalar guessing, no load rewriting and no
 * schema mutation. It repairs the exact regression where 2-3 sets disappeared
 * and RPE 6-7 became a midpoint while avoiding the broad range changes reverted
 * in PR #2250.
 */
export function getSourcePrescriptionRangeOverrides(
  source: string | null | undefined,
  blockName: string,
  countdown?: string | null,
): SourcePrescriptionRangeOverrides {
  const line = sourceBlockLine(source, blockName, countdown);
  if (!line) return { sets: null, effort: null };

  const setsMatch = line.match(/\b(\d+(?:\.\d+)?)\s*[-–—]\s*(\d+(?:\.\d+)?)\s+sets?\b/i);
  const effortMatch = line.match(/\b(RPE|RIR)\s*(\d+(?:\.\d+)?)\s*[-–—]\s*(\d+(?:\.\d+)?)\b/i);
  return {
    sets: setsMatch ? `${setsMatch[1]}-${setsMatch[2]}` : null,
    effort: effortMatch ? `${effortMatch[1].toUpperCase()} ${effortMatch[2]}-${effortMatch[3]}` : null,
  };
}

/** Put an authoritative set range back onto the existing rendered Volume row. */
export function applySourceSetRange(
  metrics: BlockMetric[],
  setsRange: string | null,
): BlockMetric[] {
  if (!setsRange) return metrics;
  return metrics.map((metric) => {
    if (metric.label !== "Volume" && metric.label !== "Duration") return metric;
    let value = metric.value.replace(/\s+per\s+set\b/i, "").trim();
    const multiplier = /^\d+(?:\.\d+)?(?:\s*[-–—]\s*\d+(?:\.\d+)?)?\s*×\s*/;
    value = multiplier.test(value)
      ? value.replace(multiplier, `${setsRange} × `)
      : `${setsRange} × ${value}`;
    return { ...metric, value };
  });
}
