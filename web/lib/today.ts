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
  tone: TodayDecisionTone;
  actionText: string;
} {
  if (state === "train_as_planned") {
    return {
      label: "Train as planned",
      icon: "GO",
      tone: "green",
      actionText: "Start session and keep the work clean.",
    };
  }
  if (state === "modify") {
    return {
      label: "Adjust",
      icon: "ADJUST",
      tone: "amber",
      actionText: "Follow adjusted work and skip extras.",
    };
  }
  if (state === "pull_back") {
    return {
      label: "Pull back",
      icon: "PULL",
      tone: "red",
      actionText: "Use recovery or light mobility today.",
    };
  }
  return {
    label: "Not checked in yet",
    icon: "CHK",
    tone: "neutral",
    actionText: "Submit the fast check-in to unlock today's recommendation.",
  };
}

export type TodayDecisionTone = "green" | "amber" | "red" | "neutral";

export type TodayDecisionDisplayState =
  | "go"
  | "adjust"
  | "pull_back"
  | "rehab_only"
  | "no_training"
  | "preview";

export type TodayDecisionBanner = {
  state: TodayRecommendationState;
  displayState: TodayDecisionDisplayState;
  chip: "GO" | "ADJUST" | "PULL BACK" | "REHAB ONLY" | "NO TRAINING" | "PREVIEW";
  /** Short coach-card headline, e.g. "Pull back today". */
  title: string;
  /** One clear reason sentence. Prefers the backend reason when present. */
  detail: string;
  /** One clear action sentence. */
  action?: string;
  /** Optional safety sentence, shown only when the backend sends one. */
  safety?: string;
  tone: TodayDecisionTone;
  blocksTraining: boolean;
};

const DECISION_BANNERS: Record<
  Exclude<TodayRecommendationState, "not_checked_in">,
  { title: string; detail: string; action: string; tone: TodayDecisionTone }
> = {
  train_as_planned: {
    title: "Sharp work ready",
    detail: "Your check-in is clear for today's combat work.",
    action: "Start session and keep the work clean.",
    tone: "green",
  },
  modify: {
    title: "Session reduced",
    detail: "Hard combat work needs to be controlled today.",
    action: "Follow adjusted work and skip extras.",
    tone: "amber",
  },
  pull_back: {
    title: "Pull back today",
    detail: "Your body is not ready for hard combat work.",
    action: "Use recovery or light mobility instead.",
    tone: "red",
  },
};

const PREVIEW_BANNER = {
  title: "Session preview",
  detail: "This session is not open today.",
  action: "Completion opens on the matched training day.",
  tone: "neutral" as const,
};

function parseBackendAdjustment(reason: string | null | undefined): {
  title?: string;
  detail?: string;
  action?: string;
  safety?: string;
} {
  const lines = (reason ?? "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length >= 3) {
    return {
      title: lines[0],
      detail: lines[1],
      action: lines[2],
      safety: lines[3],
    };
  }
  if (lines.length === 2) {
    return {
      title: lines[0],
      detail: lines[1],
    };
  }
  if (lines.length === 1) {
    return {
      detail: lines[0],
    };
  }
  return {};
}

function stripTitleStop(value: string | undefined): string | undefined {
  const text = value?.trim();
  if (!text) {
    return undefined;
  }
  return text.replace(/\.+$/g, "").trim();
}

function normalizeTitleKey(value: string | undefined): string {
  return stripTitleStop(value)?.toLowerCase() ?? "";
}

function normalizeBackendAdjustment(
  backend: ReturnType<typeof parseBackendAdjustment>,
): ReturnType<typeof parseBackendAdjustment> {
  const title = stripTitleStop(backend.title);
  const detail = backend.detail?.trim();
  const action = backend.action?.trim();
  const safety = backend.safety?.trim();

  if (
    normalizeTitleKey(backend.title) === "sharp work only" &&
    detail === "You are in taper, so sharpness matters more than extra work today." &&
    action === "Keep speed and timing work only; remove tiring rounds."
  ) {
    return {
      title: "Sharp taper work",
      detail: "Taper phase: sharpness over extra rounds.",
      action: "Keep speed and timing clean. Remove tiring rounds.",
      safety,
    };
  }

  return {
    title,
    detail,
    action,
    safety,
  };
}

function getSafetyDisplayState(
  state: TodayRecommendationState,
  backend: ReturnType<typeof parseBackendAdjustment>,
): TodayDecisionDisplayState | null {
  if (state !== "pull_back") {
    return null;
  }

  const titleKey = normalizeTitleKey(backend.title);
  const text = [backend.title, backend.detail, backend.action, backend.safety]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();

  if (
    titleKey === "no training today" ||
    text.includes("red flag") ||
    text.includes("seek medical advice")
  ) {
    return "no_training";
  }

  if (
    titleKey === "rehab only today" ||
    text.includes("injury is worse") ||
    text.includes("pain is high")
  ) {
    return "rehab_only";
  }

  return null;
}

function getDisplayState(
  state: TodayRecommendationState,
  backend: ReturnType<typeof parseBackendAdjustment>,
  isPreview: boolean,
): TodayDecisionDisplayState | null {
  const safetyState = getSafetyDisplayState(state, backend);
  if (safetyState) {
    return safetyState;
  }

  if (isPreview) {
    return "preview";
  }

  if (state === "train_as_planned") {
    return "go";
  }
  if (state === "modify") {
    return "adjust";
  }
  if (state === "pull_back") {
    return "pull_back";
  }
  return null;
}

function getDisplayTone(displayState: TodayDecisionDisplayState): TodayDecisionTone {
  if (displayState === "go") {
    return "green";
  }
  if (displayState === "adjust") {
    return "amber";
  }
  if (displayState === "preview") {
    return "neutral";
  }
  return "red";
}

function getDisplayChip(displayState: TodayDecisionDisplayState): TodayDecisionBanner["chip"] {
  if (displayState === "go") {
    return "GO";
  }
  if (displayState === "adjust") {
    return "ADJUST";
  }
  if (displayState === "pull_back") {
    return "PULL BACK";
  }
  if (displayState === "rehab_only") {
    return "REHAB ONLY";
  }
  if (displayState === "no_training") {
    return "NO TRAINING";
  }
  return "PREVIEW";
}

function displayBlocksTraining(displayState: TodayDecisionDisplayState): boolean {
  return displayState === "pull_back" || displayState === "rehab_only" || displayState === "no_training";
}

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
  options: { isPreview?: boolean } = {},
): TodayDecisionBanner | null {
  const backend = normalizeBackendAdjustment(parseBackendAdjustment(reason));
  const displayState = getDisplayState(state, backend, Boolean(options.isPreview));

  if (!displayState) {
    return null;
  }

  const banner =
    displayState === "preview"
      ? PREVIEW_BANNER
      : state === "not_checked_in"
        ? DECISION_BANNERS.train_as_planned
        : DECISION_BANNERS[state];

  return {
    state,
    displayState,
    chip: getDisplayChip(displayState),
    title: backend.title || banner.title,
    detail: backend.detail || banner.detail,
    action: backend.action || banner.action,
    safety: backend.safety,
    tone: getDisplayTone(displayState),
    blocksTraining: displayBlocksTraining(displayState),
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
