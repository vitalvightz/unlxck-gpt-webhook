// How a training day reads at a glance: its name ("Strength + Skill"), the
// parts underneath ("Fight IQ · Controlled strength") and the chips (time,
// load, exercise count). Shared by Today's session card and Home's Up Next so
// the two can never describe the same day differently.

import { athleteFacingSessionTitle, formatPlanLabel } from "@/lib/plan-labels";
import { resolveSessionTypeLabel } from "@/lib/rehab-label";
import { getBlocks, isZeroLoadSupportSession } from "@/lib/structured-plan";
import type { RehabLabelPolicy, StructuredSession } from "@/lib/types";

/** `estimate` marks a figure the plan states but nothing measured: shown "~". */
export type SummaryChip = { icon: "clock" | "load" | "exercises"; label: string; estimate?: boolean };

const LOAD_LABELS: Record<string, string> = {
  hard: "Hard",
  technical: "Technical",
  reduced: "Reduced load",
  none: "Zero load",
};

function textValue(value: string | null | undefined): string {
  return typeof value === "string" ? value.trim() : "";
}

export function sameTitle(a: string, b: string): boolean {
  const normalize = (value: string) => value.trim().toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  return Boolean(normalize(a)) && normalize(a) === normalize(b);
}

/** At-a-glance chips: total time, how hard it loads the body, and the exercise
 * count. Minutes are summed only when every session states them; otherwise the
 * backend duration stands. Session time is the plan's own estimate, never
 * derived from the prescription, so it always reads as approximate. */
export function sessionSummaryChips(
  sessions: StructuredSession[],
  fallbackDuration: string | null,
  effectiveLoad: string | null | undefined,
): SummaryChip[] {
  const minutes = sessions.map((item) => {
    const measured = item.planned_duration;
    return measured && typeof measured.value === "number" && /^min/i.test(measured.unit ?? "")
      ? measured.value
      : null;
  });
  const totalMinutes = sessions.length > 0 && minutes.every((value) => value !== null)
    ? minutes.reduce<number>((sum, value) => sum + (value ?? 0), 0)
    : null;
  const exercises = sessions.reduce((sum, item) => sum + getBlocks(item).length, 0);
  const loadKey = textValue(effectiveLoad).toLowerCase();
  const load = sessions.length > 0 && sessions.every(isZeroLoadSupportSession)
    ? "Zero load"
    : loadKey
      ? LOAD_LABELS[loadKey] ?? formatPlanLabel(loadKey)
      : "";
  const time = totalMinutes ? `${totalMinutes} min` : fallbackDuration?.replace(/^~\s*/, "") ?? null;
  const chips: Array<SummaryChip | null> = [
    time ? { icon: "clock", label: time, estimate: true } : null,
    load ? { icon: "load", label: load } : null,
    exercises > 0 ? { icon: "exercises", label: `${exercises} exercise${exercises === 1 ? "" : "s"}` } : null,
  ];
  return chips.filter((chip): chip is SummaryChip => chip !== null);
}

/** A part's type in a word or two ("Strength & Power" reads "Strength"). */
export function shortSessionType(session: StructuredSession, policy: RehabLabelPolicy | null | undefined): string {
  const label = resolveSessionTypeLabel(session, policy) || formatPlanLabel(textValue(session.session_type));
  return label.split(/\s*[&/]\s*/)[0].trim();
}

/** The parts that name a day: optional extras (the camp Fight Visualisation)
 * ride along but never name it. */
export function namedDayParts(sessions: StructuredSession[]): StructuredSession[] {
  return sessions.filter((item) => !item.optional);
}

/** "Strength + Skill" for a day of several parts, primary first; "" for one. */
export function dayPartsTitle(
  parts: StructuredSession[],
  primarySessionId: string | null | undefined,
  policy: RehabLabelPolicy | null | undefined,
): string {
  if (parts.length < 2) return "";
  const primary = parts.find((item) => item.session_id === primarySessionId) ?? parts[0];
  return Array.from(
    new Set(
      [primary, ...parts.filter((item) => item !== primary)]
        .map((item) => shortSessionType(item, policy))
        .filter(Boolean),
    ),
  ).join(" + ");
}

/** "Fight IQ · Controlled strength": the parts' own names, in training order,
 * leaving out one that only repeats the title. */
export function dayPartsSubtitle(parts: StructuredSession[], shownTitle: string): string {
  return parts
    .map((item) => athleteFacingSessionTitle(textValue(item.title)))
    .filter((title) => title && !sameTitle(title, shownTitle))
    .join(" · ");
}
