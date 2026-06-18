import type {
  TodayActiveInjury,
  TodayActivePlan,
  TodayCheckinBody,
  TodayCheckinPain,
  TodayCheckinPhase,
  TodayCheckinRequest,
  TodayCheckinSleep,
  TodayCommandView,
  TodayCompletionStatus,
  TodayPreviousSession,
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

const SESSION_VALUE_LABELS: Record<string, string> = {
  hard_as_planned: "Hard sparring",
  convert_to_technical_suggested: "Technical sparring",
  deload_suggested: "Reduced sparring",
  technical_skill: "Technical skill",
  no_hard_sparring_day: "No hard sparring",
  missing_effective_sparring_plan: "Plan detail unavailable",
  hard: "Hard session",
  technical: "Technical work",
  reduced: "Reduced work",
  none: "No training load",
};

export function formatSessionValue(value: string | null | undefined): string {
  const raw = value?.trim();
  if (!raw) {
    return "";
  }
  const normalized = raw.toLowerCase();
  if (SESSION_VALUE_LABELS[normalized]) {
    return SESSION_VALUE_LABELS[normalized];
  }
  return raw
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (match) => match.toUpperCase());
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
  activeInjury?: TodayActiveInjury;
  previousSession?: TodayPreviousSession;
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
    // Carry the athlete-reported injury/session truth so the backend safety
    // evaluator can pull back for a worsening injury or modify after a very hard
    // prior session. Defaults stay conservative-neutral when not collected.
    active_injury: params.activeInjury ?? "none",
    previous_session: params.previousSession ?? "none",
    ...params.safetyFlags,
  };
}

export function getSessionTitle(session: TodaySession): string {
  return (
    session.title?.trim() ||
    session.label?.trim() ||
    formatSessionValue(session.status) ||
    formatSessionValue(session.effective_load) ||
    "Today's session"
  );
}

export function hasTodaySession(session: TodaySession): boolean {
  return Boolean(session.session_id || session.weekday || session.status || session.title);
}

export function canCompleteTodaySession(session: TodaySession): boolean {
  if (!session.session_id) {
    return false;
  }
  // An off/rest day carries a session_id (keyed on the calendar date) but no
  // real load. Never let it be started/completed — that would persist a false
  // session state. Missing load is allowed (older payloads omit the field).
  return session.effective_load?.trim().toLowerCase() !== "none";
}

export function getVisibleRiskWatch(risks: TodayCommandView["risk_watch"]): {
  visible: TodayCommandView["risk_watch"];
  overflow: number;
} {
  const visible = risks.slice(0, 2);
  return { visible, overflow: Math.max(0, risks.length - visible.length) };
}
