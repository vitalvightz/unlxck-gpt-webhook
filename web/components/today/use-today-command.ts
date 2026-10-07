"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { getPlan, getToday } from "@/lib/api";
import { buildStructuredPlanFromText } from "@/lib/plan-text-adapter";
import { shouldRenderStructuredPlan } from "@/lib/structured-plan";
import type {
  PlanDetail,
  PlanScheduleContext,
  RehabLabelPolicy,
  ExerciseMedia,
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
  /** Curated demo videos for the active plan's blocks (PlanOutputs.exercise_media). */
  exerciseMedia: Record<string, ExerciseMedia> | null;
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
};

const EMPTY_PLAN_SCHEDULE: TodayPlanSchedule = { scheduleContext: null, createdAt: null };

const PRESENTATION_TTL_MS = 60_000;

function presentationKey(state: TodayCommandView): string {
  return JSON.stringify({
    plan: state.active_plan.id,
    day: state.today.training_day,
    // Rehab/Prehab labels follow the actual flag, not transient allocation or
    // completion decorations added by the live Today command.
    injuries: state.open_injuries.map(({ id, status, body_area, description, severity, updated_at }) =>
      ({ id, status, body_area, description, severity, updated_at })),
  });
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
  const [exerciseMedia, setExerciseMedia] = useState<Record<string, ExerciseMedia> | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const refreshSequence = useRef(0);
  const loadedPlanId = useRef<string | null>(null);
  const presentation = useRef<{ token: string; key: string; loadedAt: number } | null>(null);
  const pendingPlan = useRef<{ token: string; key: string; promise: Promise<PlanDetail | null> } | null>(null);

  const refresh = useCallback(async () => {
    if (!token) {
      return;
    }
    const sequence = ++refreshSequence.current;
    try {
      const nextState = await getToday(token);
      if (sequence !== refreshSequence.current) return;
      const activePlanId = nextState.active_plan.id;
      // Readiness and save acknowledgement must not wait for presentation data.
      // Keep the current blocks during a same-plan refresh; the server's live
      // prescription in nextState remains authoritative for training actions.
      setState(nextState);
      setError(null);
      requestXpRefresh();
      if (loadedPlanId.current !== activePlanId) {
        setStructuredPlan(null);
        setPlanSchedule(EMPTY_PLAN_SCHEDULE);
        setRehabLabelPolicy(null);
        setExerciseMedia(null);
      }
      loadedPlanId.current = activePlanId ?? null;
      const key = presentationKey(nextState);
      const loaded = presentation.current;
      if (activePlanId && loaded?.token === token && loaded.key === key
        && Date.now() - loaded.loadedAt < PRESENTATION_TTL_MS) return;
      void (async () => {
        let nextStructuredPlan: StructuredPlan | null = null;
        let nextPlanSchedule = EMPTY_PLAN_SCHEDULE;
        let nextRehabLabelPolicy: RehabLabelPolicy | null = null;
        let nextExerciseMedia: Record<string, ExerciseMedia> | null = null;

        if (activePlanId) {
          // Read-only and presentation-only: the plan supplies the blocks, the
          // schedule context and the rehab labels Today renders. Which session is
          // today is settled by the backend in `nextState` and is never
          // recomputed from this plan — see today_service.build_today_command_view.
          try {
            let pending = pendingPlan.current;
            if (pending?.token !== token || pending.key !== key) {
              pending = { token, key, promise: getPlan(token, activePlanId).catch(() => null) };
              pendingPlan.current = pending;
            }
            const detail = await pending.promise;
            if (pendingPlan.current === pending) pendingPlan.current = null;
            if (!detail) return;
            nextStructuredPlan = resolveTodayStructuredPlan(detail);
            nextPlanSchedule = {
              scheduleContext: detail?.schedule_context ?? null,
              createdAt: detail?.created_at ?? null,
            };
            nextRehabLabelPolicy = detail?.rehab_label_policy ?? null;
            nextExerciseMedia = detail?.outputs?.exercise_media ?? null;
          } catch {
            // Preserve the last good same-plan blocks on a transient read failure.
            return;
          }
        }

        if (sequence !== refreshSequence.current) return;
        presentation.current = { token, key, loadedAt: Date.now() };
        setStructuredPlan(nextStructuredPlan);
        setPlanSchedule(nextPlanSchedule);
        setRehabLabelPolicy(nextRehabLabelPolicy);
        setExerciseMedia(nextExerciseMedia);
      })();
    } catch (loadError) {
      if (sequence !== refreshSequence.current) return;
      setError(loadError instanceof Error ? loadError.message : "Today failed to load.");
    } finally {
      if (sequence === refreshSequence.current) setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    const sequenceCounter = refreshSequence;
    let cancelled = false;
    void Promise.resolve().then(() => { if (!cancelled) void refresh(); });
    return () => { cancelled = true; sequenceCounter.current++; };
  }, [refresh]);

  return {
    state,
    structuredPlan,
    planSchedule,
    rehabLabelPolicy,
    exerciseMedia,
    isLoading,
    error,
    refresh,
  };
}
