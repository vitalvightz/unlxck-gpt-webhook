import type {
  TodayActivePlan,
  TodayCheckinBody,
  TodayCheckinPain,
  TodayCheckinPhase,
  TodayCheckinRequest,
  TodayCheckinSleep,
  TodayCommandView,
  TodayCompletionStatus,
  TodayRecommendationState,
  TodaySession,
} from "@/lib/types";

type TodaySafetyFlags = {
  sharp_pain: boolean;
  instability: boolean;
  swelling: boolean;
  neurological_symptoms: boolean;
  illness_symptoms: boolean;
  cannot_warm_into_movement: boolean;
  worse_next_day_pain: boolean;
};

export const TODAY_EMPTY_TITLE = "No active plan yet";
export const TODAY_EMPTY_TEXT = "Complete intake to generate your training plan.";

export function hasActivePlan(plan: TodayActivePlan | null | undefined): boolean {
  return Boolean(plan?.id);
}

// Block 4 / PR #1800: "View full plan" opens the specific active plan, never the
// generic /plans manager. Falls back to the /plan alias (which itself resolves
// to the active plan) when the id is unavailable.
export function getActivePlanHref(plan: TodayActivePlan | null | undefined): string {
  return plan?.id ? `/plans/${plan.id}` : "/plan";
}

export function shouldShowTodayCheckin(state: TodayCommandView): boolean {
  return hasActivePlan(state.active_plan) && state.today.recommendation_state === "not_checked_in";
}

export function normalizeTodayPhase(phase: string | null | undefined): TodayCheckinPhase | null {
  if (phase === "GPP" || phase === "SPP" || phase === "TAPER" || phase === "REINTEGRATION") {
    return phase;
  }
  return null;
}

export function getRecommendationCopy(state: TodayRecommendationState): {
  label: string;
  icon: string;
  tone: string;
  actionText: string;
} {
  if (state === "train_as_planned") {
    return {
      label: "Train as planned",
      icon: "GO",
      tone: "green",
      actionText: "Execute the planned work and keep the session clean.",
    };
  }
  if (state === "modify") {
    return {
      label: "Modify",
      icon: "MOD",
      tone: "amber",
      actionText: "Use the reduced option, keep quality high, and avoid chasing volume.",
    };
  }
  if (state === "pull_back") {
    return {
      label: "Pull back",
      icon: "STOP",
      tone: "red",
      actionText: "Reduce load today. Use recovery, mobility, or coach-guided alternatives.",
    };
  }
  return {
    label: "Not checked in yet",
    icon: "CHK",
    tone: "neutral",
    actionText: "Submit the fast check-in to unlock today's backend recommendation.",
  };
}

export function getCompletionLabel(status: TodayCompletionStatus): string {
  if (status === "not_started") {
    return "Not started";
  }
  if (status === "started") {
    return "Started";
  }
  if (status === "done") {
    return "Session complete";
  }
  if (status === "modified") {
    return "Session modified";
  }
  return "Session skipped";
}

export function getCompletionActions(status: TodayCompletionStatus): string[] {
  if (status === "not_started") {
    return ["Start session", "Mark skipped"];
  }
  if (status === "started") {
    return ["Resume session", "Mark done", "Mark modified", "Mark skipped"];
  }
  if (status === "done") {
    return ["Session complete"];
  }
  if (status === "modified") {
    return ["Session modified"];
  }
  return ["Session skipped"];
}

export function completionRequiresReviewFields(status: TodayCompletionStatus): boolean {
  return status === "done" || status === "modified";
}

export function completionRequiresModificationReason(status: TodayCompletionStatus): boolean {
  return status === "modified";
}

export function buildTodayCheckinPayload(params: {
  planId: string;
  phase?: string | null;
  sleep: TodayCheckinSleep;
  body: TodayCheckinBody;
  pain: TodayCheckinPain;
  safetyFlags: TodaySafetyFlags;
}): TodayCheckinRequest {
  const phase = normalizeTodayPhase(params.phase);
  if (!phase) {
    throw new Error("Today phase is unavailable. Refresh Today before checking in.");
  }
  return {
    plan_id: params.planId,
    sleep: params.sleep,
    body: params.body,
    pain: params.pain,
    phase,
    active_injury: "none",
    previous_session: "none",
    ...params.safetyFlags,
  };
}

export function getSessionTitle(session: TodaySession): string {
  return (
    session.title?.trim() ||
    session.label?.trim() ||
    session.status?.trim() ||
    session.effective_load?.trim() ||
    "Today's session"
  );
}

export function hasTodaySession(session: TodaySession): boolean {
  return Boolean(session.session_id || session.weekday || session.status || session.title);
}

export function canCompleteTodaySession(session: TodaySession): boolean {
  return Boolean(session.session_id);
}

export function getVisibleRiskWatch(risks: TodayCommandView["risk_watch"]): {
  visible: TodayCommandView["risk_watch"];
  overflow: number;
} {
  const visible = risks.slice(0, 2);
  return { visible, overflow: Math.max(0, risks.length - visible.length) };
}
