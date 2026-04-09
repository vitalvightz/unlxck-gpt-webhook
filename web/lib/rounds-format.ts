import type { IntakeOption } from "@/lib/intake-options";

export const ROUND_COUNT_OPTIONS: IntakeOption[] = Array.from({ length: 12 }, (_, index) => ({
  label: String(index + 1),
  value: String(index + 1),
}));

export const ROUND_DURATION_OPTIONS: IntakeOption[] = [
  { label: "1 minute", value: "1" },
  { label: "2 minutes", value: "2" },
  { label: "3 minutes", value: "3" },
  { label: "5 minutes", value: "5" },
];

export type ParsedRoundsFormat = {
  roundCount: string;
  roundDuration: string;
};

const ROUNDS_FORMAT_PATTERN = /^(\d+)\s*[xX]\s*(\d+)$/;

export function parseRoundsFormat(value: string | null | undefined): ParsedRoundsFormat {
  const raw = (value ?? "").trim();
  const match = raw.match(ROUNDS_FORMAT_PATTERN);
  if (!match) {
    return { roundCount: "", roundDuration: "" };
  }
  return {
    roundCount: match[1] ?? "",
    roundDuration: match[2] ?? "",
  };
}

export function buildRoundsFormat(roundCount: string, roundDuration: string): string {
  if (!roundCount || !roundDuration) {
    return "";
  }
  return `${roundCount} x ${roundDuration}`;
}
