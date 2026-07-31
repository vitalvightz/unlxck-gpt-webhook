import {
  canCompleteTodaySession,
  getActiveSevereInjury,
  getTierMeta,
  getTodayDecisionBanner as getLegacyTodayDecisionBanner,
  hasTodaySession,
  isSessionToday,
  type TodayDecisionBanner,
  type TodayDecisionDisplayState,
  type TodayDecisionTier,
  type TodayDecisionTone,
} from "./today";
import type { TodayCommandView, TodayRecommendationState } from "./types";

export * from "./today";

type BannerOptions = {
  isPreview?: boolean;
};

type AuthoritativeDisplayState = Extract<
  TodayDecisionDisplayState,
  "go" | "adjust" | "stop" | "pull_back" | "preview"
>;

const DISPLAY_BY_DECISION: Partial<
  Record<TodayRecommendationState, Exclude<AuthoritativeDisplayState, "preview">>
> = {
  train_as_planned: "go",
  modify: "adjust",
  pull_back: "pull_back",
};

const CHIP_BY_DISPLAY: Record<
  AuthoritativeDisplayState,
  TodayDecisionBanner["chip"]
> = {
  go: "GO",
  adjust: "ADJUST",
  stop: "STOP",
  pull_back: "PULL BACK",
  preview: "PREVIEW",
};

const TONE_BY_DISPLAY: Record<
  AuthoritativeDisplayState,
  TodayDecisionTone
> = {
  go: "green",
  adjust: "amber",
  stop: "red",
  pull_back: "red",
  preview: "neutral",
};

/**
 * Backend-authoritative Today banner adapter.
 *
 * The legacy formatter is still used for display copy only. This compatibility
 * adapter normalizes state, chip and tone from the structured recommendation;
 * the shared resolver below promotes the backend decision tier over that state.
 */
export function getTodayDecisionBanner(
  state: TodayRecommendationState,
  reason?: string | null,
  options: BannerOptions = {},
): TodayDecisionBanner | null {
  const displayState = options.isPreview ? "preview" : DISPLAY_BY_DECISION[state];
  if (!displayState) {
    return null;
  }

  const copy = getLegacyTodayDecisionBanner(state, reason, options);
  if (!copy) {
    return null;
  }

  return {
    ...copy,
    displayState,
    chip: CHIP_BY_DISPLAY[displayState],
    tone: TONE_BY_DISPLAY[displayState],
  };
}

export type AuthoritativeTodayTier = Exclude<TodayDecisionTier, "preview">;

export type ResolvedTodayDecision = {
  recommendationState: TodayRecommendationState;
  authoritativeTier: AuthoritativeTodayTier;
  displayTier: TodayDecisionTier;
  banner: TodayDecisionBanner | null;
  tone: TodayDecisionTone;
  hasSession: boolean;
  sessionIsToday: boolean;
  blocksCurrentSession: boolean;
  severeInjuryBlocksCurrentSession: boolean;
  canCompleteSession: boolean;
  useSafeReplacement: boolean;
};

const FALLBACK_TIER_BY_RECOMMENDATION: Record<
  TodayRecommendationState,
  AuthoritativeTodayTier
> = {
  train_as_planned: "green",
  modify: "modify",
  pull_back: "pull_back",
  not_checked_in: "not_checked_in",
};

type ResolvedPresentationTier = Exclude<TodayDecisionTier, "not_checked_in">;

const DISPLAY_BY_TIER: Record<ResolvedPresentationTier, AuthoritativeDisplayState> = {
  stop: "stop",
  pull_back: "pull_back",
  modify: "adjust",
  green: "go",
  preview: "preview",
};

const DEFAULT_COPY_BY_TIER: Record<
  ResolvedPresentationTier,
  Pick<TodayDecisionBanner, "title" | "detail" | "action">
> = {
  stop: {
    title: "Stop today",
    detail: "A safety restriction is blocking training today.",
    action: "Do not start today's planned session. Follow the injury and safety guidance below.",
  },
  pull_back: {
    title: "Pull back today",
    detail: "Your readiness is too low for hard combat work today.",
    action: "Skip hard combat work today. Use recovery or light mobility instead.",
  },
  modify: {
    title: "Modify today",
    detail: "Your readiness is down, so reduce hard combat work today.",
    action: "Follow the adjusted work and skip extras.",
  },
  green: {
    title: "Green light",
    detail: "Your check-in is clear for today's planned work.",
    action: "Start the session and keep the work clean.",
  },
  preview: {
    title: "Session preview",
    detail: "This session is not open today.",
    action: "Completion opens on the matched training day.",
  },
};

function resolvePresentationBanner(
  recommendationState: TodayRecommendationState,
  reason: string | null | undefined,
  displayTier: TodayDecisionTier,
): TodayDecisionBanner | null {
  if (displayTier === "not_checked_in") {
    return null;
  }

  const displayState = DISPLAY_BY_TIER[displayTier];
  const fallback = DEFAULT_COPY_BY_TIER[displayTier];

  // STOP has no recommendation-state equivalent: the backend can raise it from
  // severe injury or another safety authority before check-in. Use tier-safe
  // copy so a stale or green-sounding recommendation can never contradict STOP.
  const recommendationMatchesTier =
    displayTier === "preview" ||
    FALLBACK_TIER_BY_RECOMMENDATION[recommendationState] === displayTier;
  const recommendationCopy =
    displayTier === "stop" || !recommendationMatchesTier
      ? null
      : getTodayDecisionBanner(recommendationState, reason, {
          isPreview: displayTier === "preview",
        });
  const copy = recommendationCopy ?? fallback;

  return {
    state: recommendationState,
    displayState,
    chip: CHIP_BY_DISPLAY[displayState],
    title: copy.title,
    detail: copy.detail,
    action: copy.action,
    safety: recommendationCopy?.safety,
    tone: TONE_BY_DISPLAY[displayState],
  };
}

/**
 * Resolve Today once for both presentation and session safety.
 *
 * The backend tier is authoritative. Older payloads fall back only to the
 * structured recommendation state; rendered titles, reasons and actions are
 * deliberately absent from every safety decision below.
 */
export function resolveTodayDecision(state: TodayCommandView): ResolvedTodayDecision {
  const recommendationState = state.today.recommendation_state;
  const authoritativeTier =
    state.today.decision_tier ?? FALLBACK_TIER_BY_RECOMMENDATION[recommendationState];
  const hasSession = hasTodaySession(state.today.next_session);
  const sessionIsToday = isSessionToday(
    state.today.next_session,
    state.today.session_scope,
  );
  const isPreview = !hasSession || !sessionIsToday;
  const displayTier: TodayDecisionTier = isPreview ? "preview" : authoritativeTier;
  const tone = getTierMeta(displayTier).tone;
  const banner = resolvePresentationBanner(
    recommendationState,
    state.today.recommendation_reason,
    displayTier,
  );
  const blocksCurrentSession =
    sessionIsToday &&
    (authoritativeTier === "stop" || authoritativeTier === "pull_back");
  const severeInjuryBlocksCurrentSession =
    blocksCurrentSession &&
    !state.today.injury_hold_exempt &&
    Boolean(getActiveSevereInjury(state.open_injuries));
  const canCompleteSession =
    canCompleteTodaySession(state.today.next_session) &&
    sessionIsToday &&
    !blocksCurrentSession;
  const useSafeReplacement =
    authoritativeTier === "stop" && hasSession && sessionIsToday;

  return {
    recommendationState,
    authoritativeTier,
    displayTier,
    banner,
    tone,
    hasSession,
    sessionIsToday,
    blocksCurrentSession,
    severeInjuryBlocksCurrentSession,
    canCompleteSession,
    useSafeReplacement,
  };
}

/**
 * Severe-injury and safety authority lives in the backend readiness decision and
 * command-view decision tier. The frontend must not reclassify open injuries or
 * override a server decision from severity/status fields.
 */
export function getInjuryOverrideBanner(
  _state: TodayCommandView,
  _sessionName?: string,
): TodayDecisionBanner | null {
  return null;
}
