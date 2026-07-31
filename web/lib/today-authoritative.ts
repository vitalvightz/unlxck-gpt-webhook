import {
  canCompleteTodaySession,
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
  "go" | "adjust" | "pull_back" | "preview"
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
  pull_back: "PULL BACK",
  preview: "PREVIEW",
};

const TONE_BY_DISPLAY: Record<
  AuthoritativeDisplayState,
  TodayDecisionTone
> = {
  go: "green",
  adjust: "amber",
  pull_back: "red",
  preview: "neutral",
};

/**
 * Backend-authoritative Today banner adapter.
 *
 * The legacy formatter is still used for display copy only. Safety behaviour is
 * derived exclusively from the backend recommendation state (or preview scope):
 * prose such as "red flag", "pain is high", or a changed title can never change
 * the display state, training block, chip, or tone.
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
  blocksTraining: boolean;
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
  const isPreview = state.today.next_session.session_relation === "next" || !hasSession;
  const displayTier: TodayDecisionTier = isPreview ? "preview" : authoritativeTier;
  const tone = getTierMeta(displayTier).tone;
  const copy = getTodayDecisionBanner(
    recommendationState,
    state.today.recommendation_reason,
    { isPreview },
  );
  const banner = copy ? { ...copy, tone } : null;
  const sessionIsToday = isSessionToday(
    state.today.next_session,
    state.today.session_scope,
  );
  const blocksTraining =
    authoritativeTier === "stop" || authoritativeTier === "pull_back";
  const canCompleteSession =
    canCompleteTodaySession(state.today.next_session) &&
    sessionIsToday &&
    !blocksTraining;
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
    blocksTraining,
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
