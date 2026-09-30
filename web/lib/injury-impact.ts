// Functional impact is an athlete report, not a medical diagnosis. These bands
// adapt it to the existing API; injury type, red flags and follow-ups still apply.
export const INJURY_IMPACT_OPTIONS = [
  { value: "not_limiting", label: "Not limiting me", guidedSeverity: "low", flagSeverity: "mild" },
  { value: "limiting", label: "Limiting me", guidedSeverity: "moderate", flagSeverity: "moderate" },
  { value: "cant_train", label: "Can’t train normally", guidedSeverity: "high", flagSeverity: "severe" },
] as const;
export type InjuryImpact = (typeof INJURY_IMPACT_OPTIONS)[number]["value"];

export function readInjuryImpact(text: string) {
  const value = text.match(/\[training_impact:(not_limiting|limiting|cant_train)\]/)?.[1];
  return INJURY_IMPACT_OPTIONS.find((option) => option.value === value);
}

export function writeInjuryImpact(text: string, impact: InjuryImpact | "") {
  const cleaned = text.replace(/\s?\[training_impact:[^\]]*\]/g, "").trim();
  return [cleaned, impact ? `[training_impact:${impact}]` : ""].filter(Boolean).join(" ");
}
