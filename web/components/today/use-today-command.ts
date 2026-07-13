"use client";

import { useCallback, useEffect, useState } from "react";

import { getPlan, getToday } from "@/lib/api";
import { buildStructuredPlanFromText } from "@/lib/plan-text-adapter";
import { shouldRenderStructuredPlan } from "@/lib/structured-plan";
import type {
  PlanDetail,
  PlanScheduleContext,
  StructuredPlan,
  TodayCommandView,
} from "@/lib/types";

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
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
};

const EMPTY_PLAN_SCHEDULE: TodayPlanSchedule = { scheduleContext: null, createdAt: null };

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
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!token) {
      return;
    }
    try {
      const nextState = await getToday(token);
      setState(nextState);
      setError(null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Today failed to load.");
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const activePlanId = state?.active_plan?.id;
  useEffect(() => {
    if (!token || !activePlanId) {
      setStructuredPlan(null);
      setPlanSchedule(EMPTY_PLAN_SCHEDULE);
      return;
    }
    let cancelled = false;
    getPlan(token, activePlanId)
      .then((detail) => {
        if (!cancelled) {
          setStructuredPlan(resolveTodayStructuredPlan(detail));
          setPlanSchedule({
            scheduleContext: detail?.schedule_context ?? null,
            createdAt: detail?.created_at ?? null,
          });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStructuredPlan(null);
          setPlanSchedule(EMPTY_PLAN_SCHEDULE);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token, activePlanId]);

  return { state, structuredPlan, planSchedule, isLoading, error, refresh };
}
