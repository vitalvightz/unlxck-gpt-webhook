import type { NutritionBodyweightLogEntry, NutritionWorkspaceState } from "@/lib/types";

export type BodyweightRange = "7D" | "30D" | "All";

export type IndexedBodyweightEntry = NutritionBodyweightLogEntry & {
  sourceIndex: number;
};

const RANGE_DAY_WINDOW: Record<Exclude<BodyweightRange, "All">, number> = {
  "7D": 7,
  "30D": 30,
};

function toTimestamp(entry: NutritionBodyweightLogEntry): number {
  const normalizedDate = String(entry.date || "").trim();
  if (!normalizedDate) return Number.NEGATIVE_INFINITY;
  const normalizedTime = String(entry.time || "").trim() || "00:00";
  const parsed = Date.parse(`${normalizedDate}T${normalizedTime}`);
  return Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY;
}

function normalizeWeight(value: number | null | undefined): number | null {
  if (value == null || !Number.isFinite(value)) return null;
  return Math.round(value * 10) / 10;
}

function roundToOne(value: number): number {
  return Math.round(value * 10) / 10;
}

export function getBodyweightEntriesWithIndex(entries: NutritionBodyweightLogEntry[]): IndexedBodyweightEntry[] {
  return entries
    .map((entry, sourceIndex) => ({ ...entry, sourceIndex }))
    .sort((left, right) => toTimestamp(right) - toTimestamp(left));
}

export function getLatestBodyweightEntry(entries: NutritionBodyweightLogEntry[]): NutritionBodyweightLogEntry | null {
  return getBodyweightEntriesWithIndex(entries)[0] ?? null;
}

export function getPreviousBodyweightEntry(entries: NutritionBodyweightLogEntry[]): NutritionBodyweightLogEntry | null {
  return getBodyweightEntriesWithIndex(entries)[1] ?? null;
}

export function filterBodyweightEntriesByRange(
  entries: NutritionBodyweightLogEntry[],
  range: BodyweightRange,
): NutritionBodyweightLogEntry[] {
  const sorted = getBodyweightEntriesWithIndex(entries);
  if (range === "All") {
    return sorted.map(({ sourceIndex: _sourceIndex, ...entry }) => entry);
  }

  const latest = sorted[0];
  if (!latest) return [];

  const latestTimestamp = toTimestamp(latest);
  if (!Number.isFinite(latestTimestamp)) {
    return sorted.map(({ sourceIndex: _sourceIndex, ...entry }) => entry);
  }

  const days = RANGE_DAY_WINDOW[range];
  const cutoff = latestTimestamp - (days - 1) * 24 * 60 * 60 * 1000;

  return sorted
    .filter((entry) => toTimestamp(entry) >= cutoff)
    .map(({ sourceIndex: _sourceIndex, ...entry }) => entry);
}

export function getLatestEffectiveWeight(workspace: NutritionWorkspaceState): number | null {
  const latestEntry = getLatestBodyweightEntry(workspace.nutrition_monitoring.daily_bodyweight_log);
  return normalizeWeight(latestEntry?.weight_kg ?? workspace.shared_camp_context.current_weight_kg ?? null);
}

export function getRecentChange(
  entries: NutritionBodyweightLogEntry[],
  range: BodyweightRange,
): number | null {
  const filtered = filterBodyweightEntriesByRange(entries, range);
  if (filtered.length < 2) return null;
  return roundToOne(filtered[0].weight_kg - filtered[1].weight_kg);
}

export function getTargetGap(weightKg: number | null, targetWeightKg: number | null | undefined): number | null {
  if (weightKg == null || targetWeightKg == null || !Number.isFinite(targetWeightKg)) return null;
  return roundToOne(weightKg - targetWeightKg);
}

export function getBodyMassIndex(heightCm: number | null | undefined, weightKg: number | null): number | null {
  if (heightCm == null || weightKg == null || heightCm <= 0) return null;
  const heightMeters = heightCm / 100;
  return roundToOne(weightKg / (heightMeters * heightMeters));
}

export function getSevenDayAverage(entries: NutritionBodyweightLogEntry[]): number | null {
  const recent = getBodyweightEntriesWithIndex(entries).slice(0, 7);
  if (!recent.length) return null;
  const total = recent.reduce((sum, entry) => sum + entry.weight_kg, 0);
  return roundToOne(total / recent.length);
}

export function formatWeight(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "--";
  return `${value.toFixed(1)} kg`;
}

export function formatWeightDelta(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "--";
  if (value === 0) return "Even";
  return `${value > 0 ? "+" : ""}${value.toFixed(1)} kg`;
}

export function formatTargetGapLabel(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "--";
  if (value === 0) return "On target";
  return value > 0 ? `${value.toFixed(1)} kg above` : `${Math.abs(value).toFixed(1)} kg below`;
}

export function formatBodyweightDate(value: string | null | undefined): string {
  const normalized = String(value || "").trim();
  if (!normalized) return "No entry yet";
  const parsed = new Date(`${normalized}T00:00:00`);
  if (!Number.isFinite(parsed.getTime())) return normalized;
  return new Intl.DateTimeFormat(undefined, {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(parsed);
}

export function formatBodyweightTime(value: string | null | undefined): string {
  const normalized = String(value || "").trim();
  return normalized || "No time";
}

export function formatFastedState(value: boolean | null | undefined): string {
  if (value === true) return "Fasted";
  if (value === false) return "Fed";
  return "Not set";
}

export function createBodyweightEntryKey(entry: NutritionBodyweightLogEntry, sourceIndex: number): string {
  return [entry.date, entry.time ?? "", entry.weight_kg, entry.notes ?? "", entry.is_fasted ?? "", sourceIndex].join("|");
}
