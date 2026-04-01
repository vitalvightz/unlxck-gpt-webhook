import type { GuidedInjuryInput } from "./types";

export type GuidedInjuryState = Required<GuidedInjuryInput>;

export const EMPTY_GUIDED_INJURY: GuidedInjuryState = {
  area: "",
  severity: "",
  trend: "",
  avoid: "",
  notes: "",
};

export function normalizeGuidedInjuryState(
  value: Partial<GuidedInjuryState> | null | undefined,
): GuidedInjuryState {
  return {
    area: (value?.area ?? "").trim(),
    severity: (value?.severity ?? "").trim(),
    trend: (value?.trend ?? "").trim(),
    avoid: (value?.avoid ?? "").trim(),
    notes: (value?.notes ?? "").trim(),
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
    if (!result.severity && ["low", "moderate", "high"].includes(token)) {
      result.severity = token;
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
