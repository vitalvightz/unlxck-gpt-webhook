import { normalizeGuidedInjurySeverity } from "./intake-options.ts";
import type { GuidedInjuryInput } from "./types";

export type GuidedInjuryState = Required<GuidedInjuryInput>;

function normalizeSeverityToken(token: string): "low" | "moderate" | "high" | "" {
  return normalizeGuidedInjurySeverity(token);
}

export const EMPTY_GUIDED_INJURY: GuidedInjuryState = {
  area: "",
  severity: "",
  trend: "",
  avoid: "",
  notes: "",
};

function toGuidedTextValue(value: string | null | undefined): string {
  return typeof value === "string" ? value : "";
}

export function coerceGuidedInjuryEditState(
  value: Partial<GuidedInjuryState> | null | undefined,
): GuidedInjuryState {
  return {
    area: toGuidedTextValue(value?.area),
    severity: normalizeSeverityToken(value?.severity ?? ""),
    trend: toGuidedTextValue(value?.trend),
    avoid: toGuidedTextValue(value?.avoid),
    notes: toGuidedTextValue(value?.notes),
  };
}

export function normalizeGuidedInjuryState(
  value: Partial<GuidedInjuryState> | null | undefined,
): GuidedInjuryState {
  const draft = coerceGuidedInjuryEditState(value);
  return {
    area: draft.area.trim(),
    severity: draft.severity,
    trend: draft.trend.trim(),
    avoid: draft.avoid.trim(),
    notes: draft.notes.trim(),
  };
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
  if (details.avoid) {
    parts.push(`Avoid: ${details.avoid}`);
  }
  if (details.notes) {
    parts.push(details.area || details.avoid ? `Notes: ${details.notes}` : details.notes);
  }

  return parts.join(". ").trim();
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

  if (!originalClauses.length || !generatedClauses.length) {
    return "";
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
