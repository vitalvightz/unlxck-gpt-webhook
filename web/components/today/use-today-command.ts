"use client";

import { useCallback, useEffect, useState } from "react";

import { getPlan, getPlanCompletions, getToday } from "@/lib/api";
import { resolveCurrentDay, resolveOpenPlanWeekNumber } from "@/lib/camp-map";
import { isOpenOngoingPlan } from "@/lib/plan-format";
import { buildStructuredPlanFromText } from "@/lib/plan-text-adapter";
import {
  classifySessionlessDay,
  getDays,
  getSessions,
  getWeeks,
  shouldRenderStructuredPlan,
} from "@/lib/structured-plan";
import type {
  PlanDetail,
  PlanScheduleContext,
  RehabLabelPolicy,
  StructuredDay,
  StructuredPlan,
  StructuredSession,
  TodayCommandView,
  TodaySession,
  TodaySessionCompletionRecord,
} from "@/lib/types";
import { requestXpRefresh } from "@/lib/xp-events";

/**
 * The plan Today renders blocks from: the saved server card when present,
 * otherwise the SAME deterministic plan_text adapter Plan Detail falls back to.
 * Without this fallback, a plan whose structured payload was never built left
 * Today with no session blocks at all (only the backend's sparring-day summary)
 * while Plan Detail happily showed the full week — the athlete-visible
 * "Today misses my sessions" gap.
 */
export function resolveTodayStructuredPlan(detail: PlanDetail): StructuredPlan | null {
  const saved = detail?.outputs?.structured_plan;
  if (saved && shouldRenderStructuredPlan(detail.outputs)) {
    return saved;
  }
  const planText = detail?.outputs?.plan_text?.trim();
  if (!planText) {
    return null;
  }
  return buildStructuredPlanFromText(planText, detail?.fight_date);
}

/** Plan-level timing metadata Today needs beyond the structured weeks: the
 * server schedule projection and the plan creation date. Together they anchor
 * "which week of the renewable block is it" for open (weekday-only) plans. */
export type TodayPlanSchedule = {
  scheduleContext: PlanScheduleContext | null;
  createdAt: string | null;
};

export type TodayCommand = {
  state: TodayCommandView | null;
  structuredPlan: StructuredPlan | null;
  planSchedule: TodayPlanSchedule;
  /** Per-region Rehab/Prehab policy from the same plan read. Today renders the
   * shared SessionCard, so without this every rehab block on this screen read
   * "Rehab" no matter which injuries had cleared. */
  rehabLabelPolicy: RehabLabelPolicy | null;
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
};

const EMPTY_PLAN_SCHEDULE: TodayPlanSchedule = { scheduleContext: null, createdAt: null };

const TERMINAL_COMPLETION_STATUSES = new Set(["done", "modified", "skipped"]);

function localDateFromISO(value: string): Date | null {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) {
    return null;
  }
  return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 12);
}

function completionForSession(
  completions: readonly TodaySessionCompletionRecord[],
  planId: string,
  sessionId: string,
  trainingDay: string,
): TodaySessionCompletionRecord | undefined {
  return completions.find(
    (row) =>
      row.plan_id === planId &&
      row.session_id === sessionId &&
      row.training_day === trainingDay,
  );
}

function toTodaySession(
  session: StructuredSession,
  day: StructuredDay,
  relation: "today" | "next",
  trainingDay: string,
): TodaySession | null {
  const sessionId = session.session_id?.trim();
  if (!sessionId) {
    return null;
  }
  return {
    session_id: sessionId,
    session_relation: relation,
    session_type: session.session_type,
    title: session.title?.trim() || day.today_card?.headline?.trim() || "Today's session",
    calendar_date: relation === "today" ? day.date || trainingDay : day.date,
    weekday: day.weekday || undefined,
    weekday_with_label: [day.weekday, day.countdown_label].filter(Boolean).join(" "),
    day_label: day.countdown_label || undefined,
    coach_note: session.objective || undefined,
    planned_duration: session.planned_duration,
    blocks: session.blocks,
  };
}

/**
 * Legacy plans can have a usable plan_text card but no persisted structured
 * payload. Plan Detail reconstructs that card; the Today backend cannot, so it
 * can incorrectly jump to a future schedule entry. Keep today's reconstructed
 * session authoritative until its own durable completion reaches a terminal
 * state. This is deliberately applied only when both plan and completion reads
 * succeed, so a partial read can never reopen a completed session.
 */
export function reconcileTodayWithPlanCard(
  state: TodayCommandView,
  structuredPlan: StructuredPlan | null,
  planSchedule: TodayPlanSchedule,
  completions: readonly TodaySessionCompletionRecord[],
): TodayCommandView {
  const planId = state.active_plan.id;
  const trainingDate = localDateFromISO(state.today.training_day);
  if (!planId || !structuredPlan || !trainingDate) {
    return state;
  }

  const openOngoing = isOpenOngoingPlan(state.active_plan.fight_date);
  const openWeekNumber = resolveOpenPlanWeekNumber(structuredPlan, trainingDate, {
    currentWeekNumber: planSchedule.scheduleContext?.current_week_number,
    anchorDate: planSchedule.scheduleContext?.anchor_date,
    createdAt: planSchedule.createdAt,
  });
  const current = resolveCurrentDay(structuredPlan, trainingDate, {
    openWeekNumber,
    allowDatedWeekdayMatch: openOngoing,
  });
  if (!current.inRange || !current.day) {
    return state;
  }

  const pendingSession = current.sessions.find((candidate) => {
    const sessionId = candidate.session_id?.trim();
    if (!sessionId) {
      return false;
    }
    const completion = completionForSession(
      completions,
      planId,
      sessionId,
      state.today.training_day,
    );
    return !completion || !TERMINAL_COMPLETION_STATUSES.has(completion.status);
  });
  const sessionId = pendingSession?.session_id?.trim();
  if (pendingSession && sessionId) {
    const completion = completionForSession(
      completions,
      planId,
      sessionId,
      state.today.training_day,
    );
    const reconciledSession = toTodaySession(
      pendingSession,
      current.day,
      "today",
      state.today.training_day,
    );
    if (!reconciledSession) {
      return state;
    }

    return {
      ...state,
      today: {
        ...state.today,
        next_session: reconciledSession,
        session_scope: "today",
        session_label: "Today's session",
        completion_status: completion?.status ?? "not_started",
      },
    };
  }

  // Every app session on the matched day is terminal. Derive the next card
  // from the same ordered plan the athlete sees instead of handing control back
  // to the stale schedule projection that caused the original mismatch.
  const weeks = getWeeks(structuredPlan);
  for (let weekPos = current.weekPos ?? 0; weekPos < weeks.length; weekPos += 1) {
    const days = getDays(weeks[weekPos]);
    const startDayPos = weekPos === current.weekPos ? (current.dayPos ?? -1) + 1 : 0;
    for (let dayPos = startDayPos; dayPos < days.length; dayPos += 1) {
      const nextDay = days[dayPos];
      const nextDayDate = nextDay.date?.slice(0, 10);
      const nextSession = getSessions(nextDay).find((candidate) => {
        const candidateId = candidate.session_id?.trim();
        if (!candidateId) {
          return false;
        }
        const completion = nextDayDate
          ? completionForSession(completions, planId, candidateId, nextDayDate)
          : undefined;
        return !completion || !TERMINAL_COMPLETION_STATUSES.has(completion.status);
      });
      const sessionless = classifySessionlessDay(nextDay);
      const reconciledSession = nextSession
        ? toTodaySession(nextSession, nextDay, "next", state.today.training_day)
        : sessionless.kind !== "rest"
          ? {
              session_relation: "next" as const,
              title: sessionless.title,
              status: sessionless.kind,
              calendar_date: nextDay.date,
              weekday: nextDay.weekday || undefined,
              weekday_with_label: [nextDay.weekday, nextDay.countdown_label]
                .filter(Boolean)
                .join(" "),
              day_label: nextDay.countdown_label || undefined,
              coach_led_contact: sessionless.coachLed ? sessionless.title : undefined,
            }
          : null;
      if (!reconciledSession) {
        continue;
      }
      return {
        ...state,
        today: {
          ...state.today,
          next_session: reconciledSession,
          session_scope: "next",
          session_label: "Next session",
          completion_status: "not_started",
        },
      };
    }
  }

  return {
    ...state,
    today: {
      ...state.today,
      next_session: {},
      session_scope: "none",
      session_label: "No upcoming session",
      completion_status: "not_started",
    },
  };
}

/**
 * Loads the backend Today command view and keeps it refreshable after every
 * check-in / injury / completion write. Also pulls the active plan's
 * structured_plan so Today can render today's exact session blocks from the
 * same data Plan Detail uses. The plan read is read-only and best-effort: if
 * it fails, Today still works from the backend command view (it just falls
 * back to the session summary instead of full blocks).
 */
export function useTodayCommand(token: string | null): TodayCommand {
  const [state, setState] = useState<TodayCommandView | null>(null);
  const [structuredPlan, setStructuredPlan] = useState<StructuredPlan | null>(null);
  const [planSchedule, setPlanSchedule] = useState<TodayPlanSchedule>(EMPTY_PLAN_SCHEDULE);
  const [rehabLabelPolicy, setRehabLabelPolicy] = useState<RehabLabelPolicy | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!token) {
      return;
    }
    try {
      const nextState = await getToday(token);
      const activePlanId = nextState.active_plan.id;
      let nextStructuredPlan: StructuredPlan | null = null;
      let nextPlanSchedule = EMPTY_PLAN_SCHEDULE;
      let nextRehabLabelPolicy: RehabLabelPolicy | null = null;
      let reconciledState = nextState;

      if (activePlanId) {
        // These reads are independent once Today identifies the active plan.
        // Commit their result together so a future schedule entry never flashes
        // between the Today response and the plan-card fallback arriving.
        const [planResult, completionsResult] = await Promise.allSettled([
          getPlan(token, activePlanId),
          getPlanCompletions(token, activePlanId),
        ]);
        if (planResult.status === "fulfilled") {
          const detail = planResult.value;
          nextStructuredPlan = resolveTodayStructuredPlan(detail);
          nextPlanSchedule = {
            scheduleContext: detail?.schedule_context ?? null,
            createdAt: detail?.created_at ?? null,
          };
          nextRehabLabelPolicy = detail?.rehab_label_policy ?? null;
        }
        if (planResult.status === "fulfilled" && completionsResult.status === "fulfilled") {
          reconciledState = reconcileTodayWithPlanCard(
            nextState,
            nextStructuredPlan,
            nextPlanSchedule,
            completionsResult.value.completions,
          );
        }
      }

      setStructuredPlan(nextStructuredPlan);
      setPlanSchedule(nextPlanSchedule);
      setRehabLabelPolicy(nextRehabLabelPolicy);
      setState(reconciledState);
      setError(null);
      // Every successful Today write calls this refresh. Re-read the XP progress
      // immediately so session/check-in/injury rewards do not wait for polling.
      requestXpRefresh();
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Today failed to load.");
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { state, structuredPlan, planSchedule, rehabLabelPolicy, isLoading, error, refresh };
}
