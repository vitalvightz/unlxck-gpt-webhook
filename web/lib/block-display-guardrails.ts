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

type SafetySubject = {
  part: string;
  side: "left" | "right" | null;
};

const BODY_PART_RE =
  /\b(?:(left|right)\s+)?(achilles|ankle|back|calf|chest|pec(?:toral)?|elbow|face|finger|foot|groin|adductor|hamstring|hand|head|hip|jaw|knee|neck|quad(?:riceps)?|rib(?:s)?|shin|shoulder|thigh|thumb|toe(?:s)?|wrist)\b/gi;

function canonicalBodyPart(value: string): string {
  const part = value.toLowerCase();
  if (part.startsWith("pec")) return "chest";
  if (part === "adductor") return "groin";
  if (part.startsWith("quad")) return "quad";
  if (part.startsWith("rib")) return "rib";
  if (part.startsWith("toe")) return "toe";
  return part;
}

function safetySubjects(value: string): SafetySubject[] {
  const subjects: SafetySubject[] = [];
  for (const match of value.matchAll(BODY_PART_RE)) {
    subjects.push({
      side: match[1] ? (match[1].toLowerCase() as "left" | "right") : null,
      part: canonicalBodyPart(match[2]),
    });
  }
  return subjects;
}

function subjectKey(subject: SafetySubject): string {
  return `${subject.side || "*"}:${subject.part}`;
}

function subjectsCompatible(a: readonly SafetySubject[], b: readonly SafetySubject[]): boolean {
  return a.some((left) =>
    b.some(
      (right) =>
        left.part === right.part &&
        (!left.side || !right.side || left.side === right.side),
    ),
  );
}

function globalConcepts(values: readonly string[]): Set<string> {
  const result = new Set<string>();
  for (const value of values) {
    for (const concept of safetyConcepts(value)) result.add(concept);
  }
  return result;
}

function safetyTerms(value: string): Set<string> {
  const text = normalize(value);
  const terms = new Set<string>();
  if (/\bpain\b/.test(text)) terms.add("pain");
  if (/\bbleed\w*\b/.test(text)) terms.add("bleeding");
  if (/\bredness\b/.test(text)) terms.add("redness");
  if (/\binfect\w*\b/.test(text)) terms.add("infection");
  if (/\bdrainage\b/.test(text)) terms.add("drainage");
  if (/\bwound\b/.test(text)) terms.add("wound");
  if (/\babrasion\b/.test(text)) terms.add("abrasion");
  if (/\bgraze\b/.test(text)) terms.add("graze");
  if (/\birritat\w*\b/.test(text)) terms.add("irritation");
  if (/\bswell\w*\b/.test(text)) terms.add("swelling");
  if (/\bnumb\w*\b/.test(text)) terms.add("numbness");
  if (/\btingl\w*\b/.test(text)) terms.add("tingling");
  if (/\bweakness\b/.test(text)) terms.add("weakness");
  if (/\b(?:giving way|instability)\b/.test(text)) terms.add("instability");
  return terms;
}

function hasStrongGenericOverlap(value: string, owners: readonly string[]): boolean {
  const terms = safetyTerms(value);
  if (terms.size < 2) return false;
  return owners.some((owner) => {
    const ownerTerms = safetyTerms(owner);
    let overlap = 0;
    for (const term of terms) {
      if (ownerTerms.has(term)) overlap += 1;
    }
    return overlap >= 2;
  });
}

function isOwnedSafetyClause(
  value: string,
  ownerValues: readonly string[],
  fallbackSubjectText = "",
): boolean {
  const concepts = safetyConcepts(value);
  if (concepts.size === 0) return false;

  const explicitSubjects = safetySubjects(value);
  const subjects =
    explicitSubjects.length > 0 ? explicitSubjects : safetySubjects(fallbackSubjectText);

  if (subjects.length === 0) {
    const owned = globalConcepts(ownerValues);
    return [...concepts].every((concept) => owned.has(concept));
  }

  const profiles = ownerValues.map((owner) => ({
    concepts: safetyConcepts(owner),
    subjects: safetySubjects(owner),
  }));
  const subjectProfiles = profiles.filter(
    (profile) =>
      profile.subjects.length > 0 && subjectsCompatible(subjects, profile.subjects),
  );
  const allOwnerSubjects = profiles.flatMap((profile) => profile.subjects);

  if (subjectProfiles.length === 0) {
    // If the higher-level safety copy names another body part, do not let a
    // generic symptom word such as "pain" suppress this exercise's stop rule.
    if (allOwnerSubjects.length > 0) return false;

    // Subject-less Safety Priority copy can still own an escalation clause, but
    // require more than a single generic symptom match so unrelated injuries do
    // not collapse into one another.
    return (
      [...concepts].every((concept) => globalConcepts(ownerValues).has(concept)) &&
      hasStrongGenericOverlap(value, ownerValues)
    );
  }

  const owned = new Set<string>();
  for (const profile of subjectProfiles) {
    for (const concept of profile.concepts) owned.add(concept);
  }

  // Generic safety copy may supplement a subject-specific note only when the
  // plan contains one unambiguous injury subject. With multiple body parts, fail
  // closed and keep the exercise rule unless its own subject-specific copy owns it.
  const uniqueOwnerSubjects = new Set(allOwnerSubjects.map(subjectKey));
  if (uniqueOwnerSubjects.size <= 1) {
    for (const profile of profiles) {
      if (profile.subjects.length === 0) {
        for (const concept of profile.concepts) owned.add(concept);
      }
    }
  }

  return [...concepts].every((concept) => owned.has(concept));
}

function splitStopClauses(value: string): string[] {
  return value
    .split(/\s*;\s*|,\s*(?:or\s+)?|\s+or\s+/i)
    .map((part) => part.replace(/^\s*(?:or\s+)?(?:if\s+)?/i, "").trim())
    .filter(Boolean);
}

const MAX_ATHLETE_STOP_RULE_WORDS = 10;
const STOP_RULE_EXPLANATION_TAIL_RE =
  /\s*(?:[;—–]|,)\s*(?:then\s+|and\s+then\s+)?(?:stop(?!\s+if\b)|switch|clean|cover|seek|report|modify|omit|rest|reduce|end|reassess)\b.*$/i;

function stopRuleWordCount(value: string): number {
  return value.trim().split(/\s+/).filter(Boolean).length;
}

/**
 * Keep short athlete-facing stop rules as written. For longer legacy rules,
 * remove only a clearly recognised action/explanation tail. If the remaining
 * meaningful condition is still over the prompt's ten-word target, show it in
 * full rather than cutting through a safety condition. Stored rules stay untouched.
 */
function compactAthleteStopRule(value: string): string {
  const compact = stripStopLabel(value).replace(/\s+/g, " ").trim();
  if (!compact) return "";
  if (stopRuleWordCount(compact) <= MAX_ATHLETE_STOP_RULE_WORDS) return compact;

  const withoutActionTail = compact.replace(STOP_RULE_EXPLANATION_TAIL_RE, "").trim();
  return withoutActionTail || compact;
}

/**
 * One exercise owns at most one athlete-facing stop rule. Plan-level injury and
 * red-flag copy owns global safety only when it matches the same injury subject;
 * the exercise keeps the first remaining block-specific quality/form criterion.
 * Already-saved plans are handled here at display time without mutating stored rows.
 */
export function selectCompactStopRule(
  stopRules: readonly string[],
  planSafetyTexts: readonly string[] = [],
): string | null {
  const rules = stopRules.map(stripStopLabel).filter(Boolean);
  if (rules.length === 0) return null;
  if (planSafetyTexts.length === 0) return compactAthleteStopRule(rules[0]) || null;

  for (const rule of rules) {
    if (!isOwnedSafetyClause(rule, planSafetyTexts)) {
      return compactAthleteStopRule(rule) || null;
    }
    for (const clause of splitStopClauses(rule)) {
      if (!isOwnedSafetyClause(clause, planSafetyTexts, rule)) {
        return compactAthleteStopRule(clause) || null;
      }
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

  const kept = original
    .split(/(?<=[.!?])\s+|\s*;\s*/)
    .map((part) => part.trim())
    .filter(
      (part) =>
        part &&
        !(
          ESCALATION_ACTION_RE.test(part) &&
          isOwnedSafetyClause(part, safetyPriorityTexts, original)
        ),
    );
  return kept.join(" ").trim();
}

function normalizeCountdown(value: string | null | undefined): string | null {
  const match = clean(value).toUpperCase().match(/^D-?(\d+)$/);
  return match ? `D-${Number(match[1])}` : null;
}

function countdownSection(
  source: string,
  countdown: string | null | undefined,
): string | null {
  const target = normalizeCountdown(countdown);
  if (!target) return null;

  const lines = source.split(/\r?\n/);
  const selected: string[] = [];
  let inTarget = false;

  for (const line of lines) {
    const heading = line.match(/^\s*(?:#{1,6}\s*)?(D-?\d+)\b/i);
    if (heading) {
      const label = normalizeCountdown(heading[1]);
      if (inTarget && label !== target) break;
      inTarget = label === target;
    }
    if (inTarget) selected.push(line);
  }

  return selected.length > 0 ? selected.join("\n") : null;
}

function stripSourceLineFormatting(value: string): string {
  return value
    .trim()
    .replace(/^>\s*/, "")
    .replace(/^(?:[-*+]|\d+[.)])\s+/, "")
    .replace(/[*_`]/g, "")
    .trim();
}

function isExactBlockLine(line: string, blockName: string): boolean {
  const candidate = normalize(stripSourceLineFormatting(line));
  const name = normalize(blockName);
  if (!candidate.startsWith(name)) return false;

  const remainder = candidate.slice(name.length);
  return /^\s*(?:[—–:]\s*|-\s+)/.test(remainder);
}

function sourceBlockLine(
  source: string | null | undefined,
  blockName: string,
  countdown: string | null | undefined,
): string | null {
  const raw = clean(source);
  const name = clean(blockName);
  if (!raw || !name) return null;

  // A supplied countdown is authoritative. If that section cannot be found,
  // fail closed rather than borrowing a same-named exercise from another day.
  const scoped = clean(countdown) ? countdownSection(raw, countdown) : raw;
  if (!scoped) return null;

  return (
    scoped
      .split(/\r?\n/)
      .find(
        (line) =>
          isExactBlockLine(line, name) && /\b(?:sets?|rpe|rir)\b/i.test(line),
      ) || null
  );
}

export type SourcePrescriptionRangeOverrides = {
  sets: string | null;
  effort: string | null;
};

/**
 * Recover only explicit numeric RANGES from the authoritative original plan.
 * This is deliberately narrow: no scalar guessing, no load rewriting and no
 * schema mutation. A supplied countdown and exact block title must both match;
 * otherwise the structured value remains authoritative.
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