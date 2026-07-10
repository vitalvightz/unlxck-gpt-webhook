import {
  getTodayDecisionBanner as getLegacyTodayDecisionBanner,
  type TodayDecisionBanner,
  type TodayDecisionDisplayState,
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
    blocksTraining: displayState === "pull_back",
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
