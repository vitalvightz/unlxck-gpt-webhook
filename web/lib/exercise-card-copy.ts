/**
 * Athlete-facing coaching projection only. Never mutates selected bank copy,
 * authoritative doses, safety gates, or the saved structured plan.
 */
const words = (value: string) => value.trim().split(/\s+/).filter(Boolean);
const trim = (value: string) => value.trim().replace(/[.;,\s]+$/, "");
const SHORT_MAX = 9;

export function compactCue(value: string): string {
  const source = trim(value.replace(/^\s*(?:Coach(?:ing)?\s+)?Cue:\s*/i, ""));
  if (words(source).length <= SHORT_MAX) return source;
  // The first full short instruction is a lead cue. Other stored cues remain
  // available in the canonical data, but do not become another visible section.
  const clauses = source.split(/\s*;\s*|,\s+|\s+and\s+/i);
  const lead = clauses.find((part) => words(part).length >= 2 && words(part).length <= SHORT_MAX);
  return lead ? trim(lead) : source;
}

export function compactEasier(value: string): string {
  const source = trim(value.replace(/^\s*(?:Easier|Regress(?:ion)?):\s*/i, ""));
  // Drop the explanation of the original quantity, not the prescribed target.
  const target = source
    .replace(/\s+instead of\s+.+$/i, "")
    .replace(/;\s*keep (?:effort|rest|rests).*$/i, "")
    .replace(/\s*;\s*.*$/, "");
  return words(target).length <= SHORT_MAX ? trim(target) : source;
}

export function compactProgress(value: string): string {
  const source = trim(value.replace(/^\s*Progress(?:ion)?:\s*/i, ""));
  const increment = source.match(/\badd\s+\+?\d+(?:\.\d+)?\s*(?:kg|lb|%|reps?|sets?|rounds?|m|sec|minutes?)\b(?:\s+per\s+(?:side|set))?/i);
  if (increment) {
    const step = increment[0];
    return step[0].toUpperCase() + step.slice(1);
  }
  // Do not make up a number: use only the approved future target when known.
  const nextTarget = source.match(/\b(?:increase|raise)\s+(?:rounds?|sets?|reps?|duration|work time|distance)\s+(?:only\s+)?from\s+[\d.]+\s*(?:\w+)?\s+to\s+[\d.]+\s*(?:\w+)?/i);
  if (nextTarget && words(nextTarget[0]).length <= SHORT_MAX) return nextTarget[0];
  const first = source.split(/\s*;\s*|\s*\.\s+/)[0];
  return words(first).length <= SHORT_MAX ? trim(first) : source;
}

export function compactStopText(values: readonly string[]): string | null {
  const source = values.map((v) => trim(v.replace(/^\s*Stop(?:\s+rule)?:\s*/i, ""))).filter(Boolean);
  if (!source.length) return null;
  const original = source.join("; ")
    .replace(/^(?:stop|end)\s+(?:(?:the|this)\s+)?(?:set|effort|work|hold|swim)?\s*(?:if|when|for|on)\s+/i, "")
    .replace(/^(?:if|when)\s+/i, "");
  if (words(original).length <= SHORT_MAX) return original;

  // Only recognised physical/symptom triggers can be compacted safely.
  // Unknown conditions, medical escalation and special instructions remain
  // unabridged: no UI word limit is worth hiding a safety warning.
  if (/\b(?:seek|call|clinician|medical|emergency|report|911|999)\b/i.test(original)) {
    return original;
  }
  const patterns: Array<[string, RegExp]> = [
    ["chest pain", /\bchest (?:pain|discomfort)\b/i],
    ["dizziness", /\bdizz(?:iness|y)\b/i],
    ["breathlessness", /\b(?:breathlessness|breathing difficulty|unusual breathlessness)\b/i],
    ["pain", /\bpain\b/i],
    ["lost balance", /\b(?:balance|unstable|instability|landings? become unstable)\b/i],
    ["slowing speed", /\b(?:speed drops?|speed slows?|snap speed slows|speed degrades|punch speed deteriorates)\b/i],
    ["lost form", /\b(?:form|technique|control|guard return|trunk collapses?|trunk control|shape)\b/i],
  ];
  const triggers = patterns.filter(([, pattern]) => pattern.test(original))
    .filter(([name]) => name !== "pain" || !/\bchest (?:pain|discomfort)\b/i.test(original))
    .map(([name]) => name);
  const summary = triggers.join(", ");
  return triggers.length > 0 && triggers.length <= 3 && words(summary).length <= SHORT_MAX
    ? summary : original;
}

/** A qualitative target, never a fabricated load increase or extra set. */
export function safeQualityProgress(
  blockType: string | null | undefined,
  countdown: string | null | undefined,
): string | null {
  if (!/(?:^|[_-])(?:strength|power|plyometric|conditioning|speed|accessory)(?:$|[_-])/i.test(blockType ?? "")) return null;
  const match = String(countdown ?? "").match(/D-(\d+)/i);
  // No advances inside the final ten days of camp.
  if (!match || Number(match[1]) <= 10) return null;
  return "Improve quality; maintain prescribed dose";
}
