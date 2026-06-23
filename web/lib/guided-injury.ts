import { normalizeGuidedInjurySeverity } from "./intake-options.ts";
import type { GuidedInjuryInput } from "./types";

export type GuidedInjuryState = Required<GuidedInjuryInput>;
export type GuidedInjuryHydrationSource = {
  injuries?: string | null | undefined;
  guided_injury?: Partial<GuidedInjuryState> | null | undefined;
  guided_injuries?: Array<Partial<GuidedInjuryState> | null | undefined> | null | undefined;
};
export type GuidedInjuryFields = {
  injuries: string;
  guided_injury: GuidedInjuryState | null;
  guided_injuries: GuidedInjuryState[];
};

function normalizeSeverityToken(token: string): "low" | "moderate" | "high" | "" {
  return normalizeGuidedInjurySeverity(token);
}

export const EMPTY_GUIDED_INJURY: GuidedInjuryState = {
  area: "",
  zone: "",
  severity: "",
  trend: "",
  avoid: "",
  notes: "",
  injury_type: "",
  injury_subtypes: [],
  surface_type: "",
  timeframe: "",
  cleared: "",
  open_wound: "",
  bleeding_status: "",
  infection_signs: [],
  impact_related: "",
  sensitive_area: "",
};

function toGuidedTextValue(value: string | null | undefined): string {
  return typeof value === "string" ? value : "";
}

function toGuidedStringArray(value: string[] | null | undefined): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

export function coerceGuidedInjuryEditState(
  value: Partial<GuidedInjuryState> | null | undefined,
): GuidedInjuryState {
  return {
    area: toGuidedTextValue(value?.area),
    zone: toGuidedTextValue(value?.zone),
    severity: normalizeSeverityToken(value?.severity ?? ""),
    trend: toGuidedTextValue(value?.trend),
    avoid: toGuidedTextValue(value?.avoid),
    notes: toGuidedTextValue(value?.notes),
    injury_type: toGuidedTextValue(value?.injury_type),
    injury_subtypes: toGuidedStringArray(value?.injury_subtypes),
    surface_type: toGuidedTextValue(value?.surface_type),
    timeframe: toGuidedTextValue(value?.timeframe),
    cleared: toGuidedTextValue(value?.cleared),
    open_wound: toGuidedTextValue(value?.open_wound),
    bleeding_status: toGuidedTextValue(value?.bleeding_status),
    infection_signs: toGuidedStringArray(value?.infection_signs),
    impact_related: toGuidedTextValue(value?.impact_related),
    sensitive_area: toGuidedTextValue(value?.sensitive_area),
  };
}

export function normalizeGuidedInjuryState(
  value: Partial<GuidedInjuryState> | null | undefined,
): GuidedInjuryState {
  const draft = coerceGuidedInjuryEditState(value);
  const normalizedInjuryType = draft.injury_type.trim();
  const normalizedSurfaceType = draft.surface_type.trim();
  const normalizedSubtypes = draft.injury_subtypes.map((value) => value.trim()).filter(Boolean);
  const inferredPrimarySubtype = normalizedInjuryType
    ? normalizedInjuryType === "surface_injury" && normalizedSurfaceType
      ? `surface_injury:${normalizedSurfaceType}`
      : normalizedInjuryType
    : "";
  const effectiveSubtypes = normalizedSubtypes.length
    ? normalizedSubtypes
    : inferredPrimarySubtype
      ? [inferredPrimarySubtype]
      : [];
  let effectiveInjuryType = normalizedInjuryType;
  let effectiveSurfaceType = normalizedSurfaceType;
  if (effectiveSubtypes.length === 1) {
    const [primary, secondary = ""] = effectiveSubtypes[0].split(":");
    effectiveInjuryType = primary || effectiveInjuryType;
    if (primary === "surface_injury") {
      effectiveSurfaceType = secondary || effectiveSurfaceType;
    }
  }
  return {
    area: draft.area.trim(),
    zone: draft.zone.trim(),
    severity: draft.severity,
    trend: draft.trend.trim(),
    avoid: draft.avoid.trim(),
    notes: draft.notes.trim(),
    injury_type: effectiveInjuryType,
    injury_subtypes: effectiveSubtypes,
    surface_type: effectiveSurfaceType,
    timeframe: draft.timeframe.trim(),
    cleared: draft.cleared.trim(),
    open_wound: draft.open_wound.trim(),
    bleeding_status: draft.bleeding_status.trim(),
    infection_signs: draft.infection_signs.map((value) => value.trim()).filter(Boolean),
    impact_related: draft.impact_related.trim(),
    sensitive_area: draft.sensitive_area.trim(),
  };
}

export function normalizeGuidedInjuryStates(
  values: Array<Partial<GuidedInjuryState> | null | undefined> | null | undefined,
): GuidedInjuryState[] {
  return (values ?? []).map((value) => normalizeGuidedInjuryState(value));
}

export function hasGuidedInjuryContent(value: Partial<GuidedInjuryState> | null | undefined): boolean {
  const details = normalizeGuidedInjuryState(value);
  return Boolean(
    details.area ||
      details.severity ||
      details.trend ||
      details.avoid ||
      details.notes ||
      details.injury_type ||
      details.injury_subtypes.length ||
      details.surface_type ||
      details.timeframe ||
      details.cleared ||
      details.open_wound ||
      details.bleeding_status ||
      details.infection_signs.length ||
      details.impact_related ||
      details.sensitive_area,
  );
}

export function hasGuidedInjuryDescriptorWithoutArea(
  value: Partial<GuidedInjuryState> | null | undefined,
): boolean {
  const details = normalizeGuidedInjuryState(value);
  return !details.area && Boolean(details.severity || details.trend);
}

// Injury types that always warrant a coach/admin look before release.
const SERIOUS_INJURY_TYPES = new Set([
  "fracture",
  "dislocation",
  "tendon_ligament",
  "post_surgery",
  "head_impact",
  "nerve_symptoms",
  "chest_breathing",
]);

/** True when an injury carries a serious type or a medical-safety flag (open
 * wound, won't-stop bleeding, infection signs, eye involvement) that should be
 * surfaced for review before the plan is released. Shared by the injury card's
 * inline warning and the restrictions step-level banner so they never drift. */
export function hasGuidedInjuryReviewRisk(
  value: Partial<GuidedInjuryState> | null | undefined,
): boolean {
  const injury = normalizeGuidedInjuryState(value);
  if (SERIOUS_INJURY_TYPES.has(injury.injury_type)) {
    return true;
  }
  if (injury.injury_type === "surface_injury") {
    if (injury.open_wound === "yes") return true;
    if (injury.bleeding_status === "wont_stop") return true;
    if (injury.infection_signs.some((sign) => ["pus", "fever", "spreading"].includes(sign))) return true;
    if (injury.sensitive_area === "eye") return true;
  }
  return false;
}

function normalizeGuidedText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function stripGuidedPunctuation(value: string): string {
  return normalizeGuidedText(value).replace(/^[,.;:\s]+|[,.;:\s]+$/g, "");
}

function splitGuidedSummary(raw: string): string[] {
  return raw
    .split(/\s*\.\s*/)
    .map((segment) => stripGuidedPunctuation(segment))
    .filter(Boolean);
}

function parseDescriptorText(raw: string): Pick<GuidedInjuryState, "severity" | "trend"> {
  const result: Pick<GuidedInjuryState, "severity" | "trend"> = {
    severity: "",
    trend: "",
  };

  for (const token of raw.split(",").map((value) => stripGuidedPunctuation(value).toLowerCase())) {
    const normalizedSeverity = normalizeSeverityToken(token);
    if (!result.severity && normalizedSeverity) {
      result.severity = normalizedSeverity;
      continue;
    }
    if (!result.trend && ["stable", "improving", "worsening", "getting worse"].includes(token)) {
      result.trend = token === "getting worse" ? "worsening" : token;
    }
  }

  return result;
}

function parseAreaSegment(segment: string): { area: string; severity: string; trend: string } | null {
  const trimmed = stripGuidedPunctuation(segment);
  if (!trimmed || /^(avoid|notes?)\b/i.test(trimmed)) {
    return null;
  }

  const parentheticalMatch = trimmed.match(/^(.*?)(?:\s*\(([^)]+)\))$/);
  if (parentheticalMatch) {
    const area = stripGuidedPunctuation(parentheticalMatch[1] ?? "");
    if (!area) {
      return null;
    }
    return {
      area,
      ...parseDescriptorText(parentheticalMatch[2] ?? ""),
    };
  }

  // Require whitespace on both sides of the dash so that anatomical names like
  // "Hip flexor-iliopsoas" are preserved intact as the area label.
  const dashedMatch = trimmed.match(/^(.*?)(?:\s+[-–—]\s+)(.+)$/);
  if (dashedMatch) {
    const area = stripGuidedPunctuation(dashedMatch[1] ?? "");
    const descriptors = parseDescriptorText(dashedMatch[2] ?? "");
    if (area && (descriptors.severity || descriptors.trend)) {
      return {
        area,
        ...descriptors,
      };
    }
  }

  if (trimmed.split(" ").length <= 4) {
    return {
      area: trimmed,
      severity: "",
      trend: "",
    };
  }

  return null;
}

function looksLikeDuplicateGuidedSummary(
  segment: string,
  details: Pick<GuidedInjuryState, "area" | "severity" | "trend">,
): boolean {
  if (!details.area) {
    return false;
  }

  const normalizedSegment = stripGuidedPunctuation(segment).toLowerCase();
  const normalizedArea = stripGuidedPunctuation(details.area).toLowerCase();
  if (!normalizedSegment.startsWith(normalizedArea)) {
    return false;
  }

  const descriptorHits = [details.severity, details.trend]
    .filter(Boolean)
    .map((value) => value.toLowerCase())
    .filter((value) => normalizedSegment.includes(value));

  return descriptorHits.length > 0 || normalizedSegment.includes("can train");
}

export function parseGuidedInjuryState(value: string | null | undefined): GuidedInjuryState {
  const raw = normalizeGuidedText(value ?? "");
  if (!raw) {
    return EMPTY_GUIDED_INJURY;
  }

  const nextValue = { ...EMPTY_GUIDED_INJURY };
  const avoidParts: string[] = [];
  const noteParts: string[] = [];
  const residualNotes: string[] = [];
  let captureMode: "avoid" | "notes" | null = null;

  for (const segment of splitGuidedSummary(raw)) {
    const avoidMatch = segment.match(/^(?:avoid|movements?\s+to\s+avoid)\s*:?\s*(.+)$/i);
    if (avoidMatch?.[1]) {
      avoidParts.push(stripGuidedPunctuation(avoidMatch[1]));
      captureMode = "avoid";
      continue;
    }

    const noteMatch = segment.match(/^notes?\s*:?\s*(.+)$/i);
    if (noteMatch?.[1]) {
      noteParts.push(stripGuidedPunctuation(noteMatch[1]));
      captureMode = "notes";
      continue;
    }

    if (captureMode === "avoid") {
      avoidParts.push(segment);
      continue;
    }

    if (captureMode === "notes") {
      noteParts.push(segment);
      continue;
    }

    if (!nextValue.area) {
      const parsedArea = parseAreaSegment(segment);
      if (parsedArea?.area) {
        nextValue.area = parsedArea.area;
        nextValue.severity = parsedArea.severity;
        nextValue.trend = parsedArea.trend;
        continue;
      }
    }

    if (looksLikeDuplicateGuidedSummary(segment, nextValue)) {
      continue;
    }

    residualNotes.push(segment);
  }

  if (avoidParts.length) {
    nextValue.avoid = avoidParts.join(". ");
  }

  if (noteParts.length || residualNotes.length) {
    nextValue.notes = [...noteParts, ...residualNotes].join(". ");
  }

  return normalizeGuidedInjuryState(nextValue);
}

export function buildGuidedInjurySummary(value: GuidedInjuryState): string {
  const details = normalizeGuidedInjuryState(value);
  const parts: string[] = [];

  if (details.area) {
    const descriptors = [details.severity, details.trend].filter(Boolean).join(", ");
    parts.push(descriptors ? `${details.area} (${descriptors})` : details.area);
  }
  if (details.injury_type) {
    parts.push(`Type: ${details.injury_type}`);
  }
  if (details.surface_type) {
    parts.push(`Surface: ${details.surface_type}`);
  }
  if (details.timeframe) {
    parts.push(`Timeframe: ${details.timeframe}`);
  }
  if (details.cleared) {
    parts.push(`Cleared: ${details.cleared}`);
  }
  if (details.open_wound) {
    parts.push(`Open wound: ${details.open_wound}`);
  }
  if (details.bleeding_status) {
    parts.push(`Bleeding: ${details.bleeding_status}`);
  }
  if (details.infection_signs.length) {
    parts.push(`Infection: ${details.infection_signs.join(", ")}`);
  }
  if (details.impact_related) {
    parts.push(`Impact related: ${details.impact_related}`);
  }
  if (details.sensitive_area) {
    parts.push(`Sensitive area: ${details.sensitive_area}`);
  }
  if (details.avoid) {
    parts.push(`Avoid: ${details.avoid}`);
  }
  if (details.notes) {
    parts.push(details.area || details.avoid ? `Notes: ${details.notes}` : details.notes);
  }

  return parts.join(". ").trim();
}

export function buildGuidedInjurySummaries(
  values: Array<Partial<GuidedInjuryState> | null | undefined> | null | undefined,
): string {
  return normalizeGuidedInjuryStates(values)
    .filter((value) => hasGuidedInjuryContent(value))
    .map((value) => buildGuidedInjurySummary(value))
    .filter(Boolean)
    .join(". ")
    .trim();
}

// The notes field is overloaded: it carries the athlete's free-text extra
// detail plus structured safety flags such as "[red_flags:none]". This strips
// the structured flags so only the athlete-typed prose remains.
const GUIDED_INJURY_NOTE_TAG_PATTERN = /\s?\[[a-z_]+:[^\]]*\]/gi;

/** Returns only what the athlete actually typed for one injury: the free-text
 * "what happened" description plus any free-text extra detail. It deliberately
 * omits the derived comprehension (severity, trend, type, surface, impact,
 * etc.) and the internal safety flags, so a round-trip shows the athlete their
 * own words rather than the planner's structured read of them. */
export function buildAthleteInjuryText(
  value: Partial<GuidedInjuryState> | null | undefined,
): string {
  const details = normalizeGuidedInjuryState(value);
  const freeNote = details.notes.replace(GUIDED_INJURY_NOTE_TAG_PATTERN, "").trim();
  return [details.area, freeNote].filter(Boolean).join(". ").trim();
}

/** Joins the athlete-typed text across every injury with content. */
export function buildAthleteInjuryTexts(
  values: Array<Partial<GuidedInjuryState> | null | undefined> | null | undefined,
): string {
  return normalizeGuidedInjuryStates(values)
    .filter((value) => hasGuidedInjuryContent(value))
    .map((value) => buildAthleteInjuryText(value))
    .filter(Boolean)
    .join(". ")
    .trim();
}

export function hydrateGuidedInjuryStates(source: GuidedInjuryHydrationSource): GuidedInjuryState[] {
  const nextGuidedInjuries = normalizeGuidedInjuryStates(source.guided_injuries).filter((value) =>
    hasGuidedInjuryContent(value),
  );
  if (nextGuidedInjuries.length) {
    return nextGuidedInjuries;
  }

  if (source.guided_injury && hasGuidedInjuryContent(source.guided_injury)) {
    return [normalizeGuidedInjuryState(source.guided_injury)];
  }

  const parsedLegacyInjury = parseGuidedInjuryState(source.injuries);
  return hasGuidedInjuryContent(parsedLegacyInjury) ? [parsedLegacyInjury] : [];
}

export function buildGuidedInjuryFields(
  values: Array<Partial<GuidedInjuryState> | null | undefined> | null | undefined,
  options: { noRestrictions?: boolean } = {},
): GuidedInjuryFields {
  const { noRestrictions = false } = options;
  if (noRestrictions) {
    return {
      injuries: "",
      guided_injury: null,
      guided_injuries: [],
    };
  }

  const guidedInjuries = normalizeGuidedInjuryStates(values).filter((value) => hasGuidedInjuryContent(value));
  return {
    injuries: buildGuidedInjurySummaries(guidedInjuries),
    guided_injury: guidedInjuries[0] ?? null,
    guided_injuries: guidedInjuries,
  };
}

/** Removes structured section label prefixes (e.g. "Avoid:", "Notes:") and
 * also strips a bare leading "avoid" verb as used in free-text notes (e.g.
 * "avoid deep squats") so that both formulations compare as equivalent. */
function stripInjurySectionLabels(text: string): string {
  return (
    text
      // Structured labels with colon: "Avoid:", "Notes:", "Movements to avoid:"
      .replace(/\b(?:avoid|notes?|movements?\s+to\s+avoid)\s*:\s*/gi, "")
      // Bare leading verb: "avoid deep squats" → "deep squats"
      .replace(/^\s*avoid\s+/i, "")
  );
}

/** Splits an injury string into normalised clause fragments.
 * Each fragment has label prefixes removed, parentheses expanded (so
 * "(low, stable)" and "low, stable" compare the same), punctuation stripped,
 * and whitespace collapsed – so purely formatting differences do not count. */
export function toNormalizedInjuryClauses(text: string): string[] {
  return text
    .split(/[.;]+/)
    .map((clause) =>
      stripInjurySectionLabels(clause)
        .toLowerCase()
        .replace(/[()]/g, " ")
        .replace(/[^\w\s]/g, " ")
        .replace(/\s+/g, " ")
        .trim(),
    )
    .filter(Boolean);
}

export function getInjuryMismatchContextKey(original: string, generated: string): string {
  const originalClauses = toNormalizedInjuryClauses(original);
  const generatedClauses = toNormalizedInjuryClauses(generated);

  if (!originalClauses.length) {
    return "";
  }

  if (!generatedClauses.length) {
    return JSON.stringify({
      original: originalClauses,
      generated: [],
    });
  }

  for (const clause of originalClauses) {
    if (!clauseIsCovered(clause, generatedClauses)) {
      return JSON.stringify({
        original: originalClauses,
        generated: generatedClauses,
      });
    }
  }

  return "";
}

/** Returns true when needle is semantically present in at least one haystack item. */
function clauseIsCovered(needle: string, haystack: string[]): boolean {
  return haystack.some((h) => h === needle || h.includes(needle));
}

/** Returns true when the original injury text contains meaningful content that
 * is absent from the generated summary (indicating content would be dropped).
 * Purely formatting differences – capitalisation, punctuation, label prefixes
 * like "Avoid:" / "Notes:", and parenthetical descriptor groups – do not
 * constitute a meaningful mismatch. */
export function hasMeaningfulInjuryMismatch(original: string, generated: string): boolean {
  return Boolean(getInjuryMismatchContextKey(original, generated));
}
