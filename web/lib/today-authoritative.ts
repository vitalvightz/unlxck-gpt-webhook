import {
  canCompleteTodaySession,
  getActiveSevereInjury,
  getInjuryOverrideBanner as getLegacyInjuryOverrideBanner,
  getSessionTitle,
  getTierMeta,
  getTodayDecisionBanner as getLegacyTodayDecisionBanner,
  hasTodaySession,
  isSessionToday,
  type TodayDecisionBanner,
  type TodayDecisionDisplayState,
  type TodayDecisionTier,
  type TodayDecisionTone,
} from "./today";
import type {
  TodayCommandView,
  TodayRecommendationState,
  TodaySession,
} from "./types";

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
  { title: string; detail: string; action: string }
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

type CanonicalSessionType =
  | "strength_power"
  | "conditioning"
  | "skill"
  | "sparring"
  | "primer"
  | "recovery"
  | "rehab"
  | "fight_or_match"
  | "mixed";

type SupportInsertCategory =
  | "tactical"
  | "mental"
  | "recovery"
  | "mobility"
  | "movement_quality"
  | "technical"
  | "footwork"
  | "recovery_walk"
  | "conditioning_maintenance";

type CanonicalBlockType =
  | "preparation"
  | "mobility_activation"
  | "plyometric_power"
  | "speed"
  | "strength"
  | "strength_speed"
  | "accessory"
  | "conditioning"
  | "skill"
  | "sparring"
  | "cooldown_recovery"
  | "nutrition"
  | "mindset"
  | "rehab";

const PREVIEW_ACTION_BY_SESSION_TYPE = {
  strength_power: "Review the lifts and loading before it opens.",
  conditioning: "Review the intervals and pace before it opens.",
  skill: "Review the drills and technical focus before it opens.",
  sparring: "Review the rounds and contact plan before it opens.",
  primer: "Review the primer and key movement cues before it opens.",
  recovery: "Review the mobility and recovery work before it opens.",
  rehab: "Review the rehab sequence and pain-free ranges before it opens.",
  fight_or_match: "Review the fight-day plan before it opens.",
  mixed: "Review the session blocks and transitions before it opens.",
} satisfies Record<CanonicalSessionType, string>;

const PREVIEW_ACTION_BY_SUPPORT_CATEGORY = {
  tactical: "Review the tactical cues before it opens.",
  mental: "Review the mindset work before it opens.",
  recovery: "Review the recovery work before it opens.",
  mobility: "Review the mobility work and pain-free ranges before it opens.",
  movement_quality: "Review the movement-quality work before it opens.",
  technical: "Review the technical drills before it opens.",
  footwork: "Review the footwork pattern before it opens.",
  recovery_walk: "Review the easy pace and route before it opens.",
  conditioning_maintenance: "Review the easy conditioning pace before it opens.",
} satisfies Record<SupportInsertCategory, string>;

const PREVIEW_ACTION_BY_BLOCK_TYPE = {
  preparation: "Review the preparation sequence before it opens.",
  mobility_activation: "Review the mobility and activation work before it opens.",
  plyometric_power: "Review the explosive work and rest periods before it opens.",
  speed: "Review the speed work and rest periods before it opens.",
  strength: "Review the lifts and loading before it opens.",
  strength_speed: "Review the power lifts and loading before it opens.",
  accessory: "Review the accessory work before it opens.",
  conditioning: "Review the intervals and pace before it opens.",
  skill: "Review the drills and technical focus before it opens.",
  sparring: "Review the rounds and contact plan before it opens.",
  cooldown_recovery: "Review the cooldown and recovery work before it opens.",
  nutrition: "Review the nutrition steps before it opens.",
  mindset: "Review the mindset cues before it opens.",
  rehab: "Review the rehab sequence and pain-free ranges before it opens.",
} satisfies Record<CanonicalBlockType, string>;

function normalizedSessionToken(value: unknown): string {
  return typeof value === "string"
    ? value.trim().toLowerCase().replace(/[\s-]+/g, "_")
    : "";
}

function getPreviewAction(session: TodaySession | null | undefined): string {
  const supportCategory = normalizedSessionToken(session?.support_insert_category);
  if (supportCategory in PREVIEW_ACTION_BY_SUPPORT_CATEGORY) {
    return PREVIEW_ACTION_BY_SUPPORT_CATEGORY[
      supportCategory as SupportInsertCategory
    ];
  }

  const sessionType = normalizedSessionToken(session?.session_type);
  if (sessionType in PREVIEW_ACTION_BY_SESSION_TYPE) {
    return PREVIEW_ACTION_BY_SESSION_TYPE[sessionType as CanonicalSessionType];
  }

  const blockActions = (session?.blocks ?? [])
    .map((block) => {
      const blockType = normalizedSessionToken(block.block_type);
      return blockType in PREVIEW_ACTION_BY_BLOCK_TYPE
        ? PREVIEW_ACTION_BY_BLOCK_TYPE[blockType as CanonicalBlockType]
        : null;
    })
    .filter((action): action is string => Boolean(action));
  const uniqueBlockActions = [...new Set(blockActions)];
  if (uniqueBlockActions.length === 1) {
    return uniqueBlockActions[0] ?? DEFAULT_COPY_BY_TIER.preview.action;
  }
  if (uniqueBlockActions.length > 1) {
    return PREVIEW_ACTION_BY_SESSION_TYPE.mixed;
  }

  return DEFAULT_COPY_BY_TIER.preview.action;
}

function getPreviewCopy(
  session: TodaySession | null | undefined,
): { title: string; detail: string; action: string } {
  if (!session || !hasTodaySession(session)) {
    return DEFAULT_COPY_BY_TIER.preview;
  }

  return {
    title: DEFAULT_COPY_BY_TIER.preview.title,
    detail: `${getSessionTitle(session)} is next on your plan.`,
    action: getPreviewAction(session),
  };
}

function resolvePresentationBanner(
  recommendationState: TodayRecommendationState,
  reason: string | null | undefined,
  displayTier: TodayDecisionTier,
  injuryPresentation?: TodayDecisionBanner | null,
  previewSession?: TodaySession | null,
): TodayDecisionBanner | null {
  if (displayTier === "not_checked_in") {
    return null;
  }

  const displayState = DISPLAY_BY_TIER[displayTier];
  const fallback = DEFAULT_COPY_BY_TIER[displayTier];

  // Today's readiness and injuries say nothing authoritative about a future
  // session. A preview is framed only from the session being previewed.
  if (displayTier === "preview") {
    const copy = getPreviewCopy(previewSession);
    return {
      state: recommendationState,
      displayState,
      chip: CHIP_BY_DISPLAY[displayState],
      ...copy,
      tone: TONE_BY_DISPLAY[displayState],
    };
  }

  // STOP has no recommendation-state equivalent: the backend can raise it from
  // severe injury or another safety authority before check-in. Use tier-safe
  // copy so a stale or green-sounding recommendation can never contradict STOP.
  const recommendationMatchesTier =
    FALLBACK_TIER_BY_RECOMMENDATION[recommendationState] === displayTier;
  const recommendationCopy =
    displayTier === "stop" || !recommendationMatchesTier
      ? null
      : getTodayDecisionBanner(recommendationState, reason, {
          isPreview: false,
        });
  const injuryCopy =
    displayTier === "stop" ? injuryPresentation ?? null : null;
  const copy = injuryCopy ?? recommendationCopy ?? fallback;

  return {
    state: recommendationState,
    displayState,
    chip: CHIP_BY_DISPLAY[displayState],
    title: injuryCopy ? fallback.title : copy.title,
    detail: copy.detail,
    action: copy.action,
    safety: injuryCopy?.safety ?? recommendationCopy?.safety,
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
  // Injury data can make a backend-authoritative STOP more specific, but it
  // never creates the STOP. This preserves truthful injury presentation while
  // keeping the server decision tier as the sole safety authority.
  const injuryPresentation =
    authoritativeTier === "stop" && !isPreview
      ? getLegacyInjuryOverrideBanner(
          state,
          hasSession ? getSessionTitle(state.today.next_session) : undefined,
        )
      : null;
  const banner = resolvePresentationBanner(
    recommendationState,
    state.today.recommendation_reason,
    displayTier,
    injuryPresentation,
    state.today.next_session,
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
 * Preserve the legacy presentation helper for consumers outside the shared
 * resolver. Its result is display data only and must never determine session
 * safety; resolveTodayDecision keeps that authority with decision_tier.
 */
export function getInjuryOverrideBanner(
  state: TodayCommandView,
  sessionName?: string,
): TodayDecisionBanner | null {
  return getLegacyInjuryOverrideBanner(state, sessionName);
}
