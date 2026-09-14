"use client";

import { useCallback, useEffect, useState } from "react";

import { getPlan, getToday } from "@/lib/api";
import { buildStructuredPlanFromText } from "@/lib/plan-text-adapter";
import { shouldRenderStructuredPlan } from "@/lib/structured-plan";
import type {
  PlanDetail,
  PlanScheduleContext,
  RehabLabelPolicy,
  StructuredPlan,
  TodayCommandView,
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

      if (activePlanId) {
        // Read-only and presentation-only: the plan supplies the blocks, the
        // schedule context and the rehab labels Today renders. Which session is
        // today is settled by the backend in `nextState` and is never
        // recomputed from this plan — see today_service.build_today_command_view.
        try {
          const detail = await getPlan(token, activePlanId);
          nextStructuredPlan = resolveTodayStructuredPlan(detail);
          nextPlanSchedule = {
            scheduleContext: detail?.schedule_context ?? null,
            createdAt: detail?.created_at ?? null,
          };
          nextRehabLabelPolicy = detail?.rehab_label_policy ?? null;
        } catch {
          // Today still works from the command view alone.
        }
      }

      setStructuredPlan(nextStructuredPlan);
      setPlanSchedule(nextPlanSchedule);
      setRehabLabelPolicy(nextRehabLabelPolicy);
      setState(nextState);
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
