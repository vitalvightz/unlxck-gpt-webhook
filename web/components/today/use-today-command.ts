"use client";

import { useCallback, useEffect, useState } from "react";

import { getPlan, getPlanCompletions, getToday } from "@/lib/api";
import { resolveCurrentDay, resolveOpenPlanWeekNumber } from "@/lib/camp-map";
import { isOpenOngoingPlan } from "@/lib/plan-format";
import { buildStructuredPlanFromText } from "@/lib/plan-text-adapter";
import { shouldRenderStructuredPlan } from "@/lib/structured-plan";
import type {
  PlanDetail,
  PlanScheduleContext,
  RehabLabelPolicy,
  StructuredPlan,
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
    const completion = completions.find(
      (row) =>
        row.plan_id === planId &&
        row.session_id === sessionId &&
        row.training_day === state.today.training_day,
    );
    return !completion || !TERMINAL_COMPLETION_STATUSES.has(completion.status);
  });
  const sessionId = pendingSession?.session_id?.trim();
  if (!pendingSession || !sessionId) {
    return state;
  }

  const completion = completions.find(
    (row) =>
      row.plan_id === planId &&
      row.session_id === sessionId &&
      row.training_day === state.today.training_day,
  );
  const reconciledSession: TodaySession = {
    session_id: sessionId,
    session_relation: "today",
    session_type: pendingSession.session_type,
    title: pendingSession.title?.trim() || current.day.today_card?.headline?.trim() || "Today's session",
    calendar_date: current.day.date || state.today.training_day,
    weekday: current.day.weekday || undefined,
    weekday_with_label: [current.day.weekday, current.day.countdown_label].filter(Boolean).join(" "),
    day_label: current.day.countdown_label || undefined,
    coach_note: pendingSession.objective || undefined,
    planned_duration: pendingSession.planned_duration,
    blocks: pendingSession.blocks,
  };

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
