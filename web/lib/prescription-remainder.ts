import type { BlockMetric } from "./structured-plan";

const quantity = String.raw`\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?`;
const timeUnit = String.raw`(?:seconds?|secs?|s|minutes?|mins?|min)`;
const volumePrefix = new RegExp(String.raw`^(${quantity})\s*(?:sets?\s*)?[x×]\s*(${quantity})\s*(?:reps?\b)?`, "i");
const timePrefix = new RegExp(String.raw`^(?:(rest|recovery|reset|work|duration|between[- ]block rest)\s*:?\s*)?(${quantity})\s*(${timeUnit})\b\s*(?:(rest|recovery|reset|work|between blocks)\b)?`, "i");
const effortPrefix = new RegExp(String.raw`^(?:RPE|RIR)\s*${quantity}(?:\s*/\s*10)?\b`, "i");

function key(text: string): string {
  return text.toLowerCase().replace(/×/g, "x").replace(/[–—]/g, "-")
    .replace(/[.]$/, "").replace(/\b(?:sets?|reps?|volume)\b/g, "").replace(/[^a-z0-9%/.-]+/g, "");
}

function seconds(value: string): number | null {
  const match = value.match(new RegExp(String.raw`^\s*(\d+(?:\.\d+)?)\s*(${timeUnit})\s*$`, "i"));
  return match ? Number(match[1]) * (/^m/i.test(match[2]) ? 60 : 1) : null;
}

/** Remove only dose fragments proved visible on this card. Unrecognised prose,
 * ranges, tempo, side instructions and safety qualifiers remain source text.
 * Merely having some metrics is never proof that a legacy dose is complete. */
export function prescriptionRemainder(text: string | null, metrics: readonly BlockMetric[], visibleText: readonly string[] = []): string | null {
  if (!text) return null;
  const displayed = new Set([...visibleText, ...metrics.flatMap(metric => [metric.value, `${metric.label} ${metric.value}`])].map(key));
  const metric = (label: string) => metrics.find(entry => entry.label === label)?.value;
  const pieces = text.split(/[;,\n]+|\s+\/\s+/).flatMap(piece => {
    let rest = piece.trim().replace(/[.]$/, "");
    if (!rest || displayed.has(key(rest))) return [];
    // Only a dose-led clause may lose quantities. "Never exceed 3 sets" is
    // an instruction, not a disposable copy of the Volume metric.
    if (!/^(?:\d|rest\b|recovery\b|reset\b|work\b|duration\b|load\b|RPE\b|RIR\b|between[- ]block rest\b)/i.test(rest)) return [piece.trim()];
    rest = rest.replace(volumePrefix, match => key(match) === key(metric("Volume") ?? "") ? "" : match).trim();
    rest = rest.replace(new RegExp(String.raw`^(${quantity})\s+(rounds?|blocks?)\b\s*(?:of\b|[x×])?`, "i"), (match, count, noun) =>
      key(count) === key(metric(/^round/i.test(noun) ? "Rounds" : "Blocks") ?? "") ? "" : match).trim();
    rest = rest.replace(timePrefix, (match, before, count, unit, after) => {
      const label = `${before ?? ""} ${after ?? ""}`;
      const target = /between/i.test(label) ? metric("Between blocks")
        : /rest|recovery|reset/i.test(label) ? metric("Rest")
          : /work/i.test(label) ? metric("Work") : metric("Duration") ?? metric("Work");
      const source = seconds(`${count} ${unit}`);
      return source !== null && source === seconds(target ?? "") ? "" : match;
    }).trim();
    rest = rest.replace(/^(?:(?:load\s*:?)|@)?\s*(\d+(?:\.\d+)?\s*(?:%\s*(?:1RM|rep max)?|kg|lbs?))\b/i, (match, value) =>
      key(value) === key(metric("Load") ?? "") ? "" : match).trim();
    rest = rest.replace(effortPrefix, match =>
      key(match) === key(metric("Effort") ?? "") ? "" : match).trim();
    if (!rest || displayed.has(key(rest))) return [];
    return [rest];
  });
  return [...new Set(pieces)].join("; ") || null;
}
