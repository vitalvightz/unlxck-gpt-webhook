"use client";

import { useCallback, useEffect, useState } from "react";

import { buildStructuredPlanFromText } from "@/components/plan-viewer";
import { getPlan, getToday } from "@/lib/api";
import { shouldRenderStructuredPlan } from "@/lib/structured-plan";
import type { PlanDetail, StructuredPlan, TodayCommandView } from "@/lib/types";

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

export type TodayCommand = {
  state: TodayCommandView | null;
  structuredPlan: StructuredPlan | null;
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
};

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
      return;
    }
    let cancelled = false;
    getPlan(token, activePlanId)
      .then((detail) => {
        if (!cancelled) {
          setStructuredPlan(resolveTodayStructuredPlan(detail));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStructuredPlan(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token, activePlanId]);

  return { state, structuredPlan, isLoading, error, refresh };
}
