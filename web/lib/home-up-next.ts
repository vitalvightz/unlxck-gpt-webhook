import { resolveCurrentDay, resolveOpenPlanWeekNumber } from "@/lib/camp-map";
import {
  dayPartsSubtitle,
  dayPartsTitle,
  getSessionDurationLabel,
  namedDayParts,
  resolveLiveDaySessions,
  sessionSummaryChips,
  type SummaryChip,
} from "@/lib/session-summary";
import { getSessionTitle, resolveSessionFocusDate } from "@/lib/today";
import type { RehabLabelPolicy, StructuredPlan, StructuredSession, TodayCommandView } from "@/lib/types";

export type UpNextSummary = {
  sessions: StructuredSession[];
  title: string;
  subtitle: string;
  chips: SummaryChip[];
};

/**
 * Home's Up next card: the day the command view points at, resolved exactly
 * as Today resolves it (an athlete-owned live day keeps its saved sessions),
 * so both screens show the same parts, exercise count and duration.
 */
export function resolveUpNextSummary({
  state,
  structuredPlan,
  trainingDay,
  openOngoing,
  scheduleHints,
  policy,
}: {
  state: TodayCommandView | null | undefined;
  structuredPlan: StructuredPlan | null;
  trainingDay: Date | null;
  openOngoing: boolean;
  scheduleHints?: Parameters<typeof resolveOpenPlanWeekNumber>[2];
  policy: RehabLabelPolicy | null | undefined;
}): UpNextSummary {
  const nextSession = state?.today?.next_session ?? null;
  const focusDate = resolveSessionFocusDate(trainingDay, nextSession);
  const focusDay = resolveCurrentDay(structuredPlan, focusDate, {
    openWeekNumber: resolveOpenPlanWeekNumber(structuredPlan, focusDate, scheduleHints),
    allowDatedWeekdayMatch: openOngoing,
  });
  const sessions = resolveLiveDaySessions(focusDay.inRange ? focusDay.sessions : [], state?.live_prescription);
  const parts = namedDayParts(sessions);
  const title =
    dayPartsTitle(parts, nextSession?.session_id, policy) ||
    (nextSession ? getSessionTitle(nextSession) : "") ||
    "Rest day";
  return {
    sessions,
    title,
    subtitle: dayPartsSubtitle(parts, title),
    chips: sessionSummaryChips(sessions, getSessionDurationLabel(nextSession), nextSession?.effective_load),
  };
}
