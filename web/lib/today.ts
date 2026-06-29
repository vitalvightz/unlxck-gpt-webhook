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

export type TodayDecisionBanner = {
  state: TodayRecommendationState;
  /** Short command headline, e.g. "PULL BACK TODAY". */
  title: string;
  /** One command-like line. Prefers the backend reason when present. */
  detail: string;
  tone: string;
};

const DECISION_BANNERS: Record<
  Exclude<TodayRecommendationState, "not_checked_in">,
  { title: string; detail: string; tone: string }
> = {
  train_as_planned: {
    title: "TRAIN AS PLANNED",
    detail: "Readiness is acceptable. Complete today's prescribed session.",
    tone: "green",
  },
  modify: {
    title: "MODIFY SESSION",
    detail: "Use the safer version today. Remove high-impact work and keep output controlled.",
    tone: "amber",
  },
  pull_back: {
    title: "PULL BACK TODAY",
    detail: "Reduce load and intensity. Keep the session technical. Stop if pain rises.",
    tone: "red",
  },
};

/**
 * The compact decision banner shown above today's session blocks once the
 * athlete has checked in. Returns null before check-in (no decision yet). The
 * banner title is fixed and command-like; the detail prefers the backend
 * readiness reason and falls back to the canned command copy. This does not
 * mutate the plan — it only frames the original blocks as train/modify/pull-back.
 */
export function getTodayDecisionBanner(
  state: TodayRecommendationState,
  reason?: string | null,
): TodayDecisionBanner | null {
  if (state === "not_checked_in") {
    return null;
  }
  const banner = DECISION_BANNERS[state];
  return {
    state,
    title: banner.title,
    detail: reason?.trim() || banner.detail,
    tone: banner.tone,
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

/**
 * Human-readable focus line for a session — never a raw backend enum. Prefers
 * the plain-language focus/emphasis fields and only falls back to the humanized
 * load value, then coach copy. Shared by Today and Overview so both agree.
 */
export function getSessionFocus(session: TodaySession): string {
  return (
    session.primary_focus?.trim() ||
    session.emphasis?.trim() ||
    formatSessionValue(session.effective_load) ||
    session.reason?.trim() ||
    session.coach_note?.trim() ||
    "Follow the current plan guidance."
  );
}

/**
 * Short supporting day line, e.g. "Thu · D-17". Keeps the weekday/countdown
 * visible as a sub-label so the session type can headline the card instead.
 */
export function getSessionDayLabel(session: TodaySession): string {
  const dayText = (session.weekday_with_label || session.weekday || "").trim();
  const countdown =
    typeof session.d_day === "number" ? `D-${Math.abs(session.d_day)}` : (session.day_label || "").trim();
  const hasCountdownInDayText = Boolean(dayText && countdown && dayText.includes(countdown));
  const parts = [dayText, hasCountdownInDayText ? "" : countdown].filter(Boolean);
  return parts.join(" · ");
}

export function hasTodaySession(session: TodaySession): boolean {
  return Boolean(session.session_id || session.weekday || session.status || session.title);
}

/**
 * The calendar day the structured-plan view (Today's blocks, Plan's "Today"
 * highlight) should center on. Normally the athlete-local `trainingDay`, but once
 * the backend command view has advanced past today's session — today logged as
 * done/modified/skipped, or a coach-led / rest day that carries no app card — the
 * `next_session` it returns carries `session_relation: "next"` plus the next
 * scheduled session's `calendar_date`. Centering the structured resolver on that
 * day keeps Today and Plan aligned with Overview's "Next session" instead of
 * sticking on the completed/empty current day (the original bug: the header
 * advanced to "Next scheduled session" while the card body kept the finished
 * day). Falls back to `trainingDay` whenever the next session has no usable
 * calendar date (e.g. weekday-only undated plans).
 */
export function resolveSessionFocusDate(
  trainingDay: Date | null,
  session: TodaySession | null | undefined,
): Date | null {
  if (session?.session_relation === "next") {
    const iso = (session.calendar_date || "").slice(0, 10);
    if (iso) {
      const focus = new Date(`${iso}T12:00:00`);
      if (!Number.isNaN(focus.getTime())) {
        return focus;
      }
    }
  }
  return trainingDay;
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
