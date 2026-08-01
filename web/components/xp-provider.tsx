"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { useAppSession } from "@/components/auth-provider";
import { claimDailyLoginXp } from "@/lib/api";
import { createFreshXpState, type XpAwardResult, type XpState } from "@/lib/xp";

export type XpDailyRewardStatus = "pending" | "earned" | "unavailable";

type XpContextValue = {
  state: XpState;
  isHydrated: boolean;
  dailyRewardStatus: XpDailyRewardStatus;
  isNewAward: boolean;
  isNewDailyAward: boolean;
  previousTotalXp: number;
  refresh: () => Promise<void>;
};

type XpViewState = Omit<XpContextValue, "refresh"> & {
  athleteId: string | null;
};

type ClaimDailyOptions = {
  respectCooldown: boolean;
};

export const XP_AUTOMATIC_CLAIM_COOLDOWN_MS = 5 * 60 * 1_000;

const initialViewState = (): XpViewState => ({
  athleteId: null,
  state: createFreshXpState(),
  isHydrated: false,
  dailyRewardStatus: "pending",
  isNewAward: false,
  isNewDailyAward: false,
  previousTotalXp: 0,
});

export const XpContext = createContext<XpContextValue | undefined>(undefined);

export function XpProvider({ children }: Readonly<{ children: ReactNode }>) {
  const { me, session } = useAppSession();
  const athleteId = me?.profile.role === "athlete" ? me.profile.athlete_id.trim() : "";
  const accessToken = session?.access_token ?? "";
  const identityKey = athleteId && accessToken ? `${athleteId}:${accessToken}` : "";
  const [view, setView] = useState<XpViewState>(initialViewState);
  const activeIdentityRef = useRef(identityKey);
  const activeAthleteRef = useRef(athleteId);
  const inFlightRef = useRef<{ key: string; request: Promise<void> } | null>(null);
  const lastClaimCompletedAtRef = useRef(0);

  useEffect(() => {
    activeIdentityRef.current = identityKey;
    if (activeAthleteRef.current === athleteId) {
      return;
    }

    activeAthleteRef.current = athleteId;
    lastClaimCompletedAtRef.current = 0;
    inFlightRef.current = null;
    setView({
      ...initialViewState(),
      athleteId: athleteId || null,
      isHydrated: !athleteId,
    });
  }, [athleteId, identityKey]);

  const applyResult = useCallback((result: XpAwardResult, targetAthleteId: string) => {
    const isNewAward = Boolean(result.awarded && result.award);
    setView({
      athleteId: targetAthleteId,
      state: result.state,
      isHydrated: true,
      dailyRewardStatus: result.state.lastDailyLoginDate ? "earned" : "pending",
      isNewAward,
      isNewDailyAward: isNewAward && result.award?.action === "daily_login",
      previousTotalXp: isNewAward ? result.previousTotalXp : result.state.totalXp,
    });
  }, []);

  const claimDaily = useCallback(async ({ respectCooldown }: ClaimDailyOptions) => {
    if (!athleteId || !accessToken || !identityKey) {
      return;
    }

    if (
      respectCooldown &&
      lastClaimCompletedAtRef.current > 0 &&
      Date.now() - lastClaimCompletedAtRef.current < XP_AUTOMATIC_CLAIM_COOLDOWN_MS
    ) {
      return;
    }

    if (inFlightRef.current?.key === identityKey) {
      try {
        await inFlightRef.current.request;
      } finally {
        if (activeAthleteRef.current === athleteId) {
          lastClaimCompletedAtRef.current = Date.now();
        }
      }
      return;
    }

    const targetAthleteId = athleteId;
    const targetIdentityKey = identityKey;
    const request = (async () => {
      try {
        const result = await claimDailyLoginXp(accessToken);
        if (activeIdentityRef.current === targetIdentityKey) {
          applyResult(result, targetAthleteId);
        }
      } catch {
        if (activeIdentityRef.current !== targetIdentityKey) {
          return;
        }
        setView((current) => ({
          athleteId: targetAthleteId,
          state: current.athleteId === targetAthleteId ? current.state : createFreshXpState(),
          isHydrated: true,
          dailyRewardStatus: "unavailable",
          isNewAward: false,
          isNewDailyAward: false,
          previousTotalXp:
            current.athleteId === targetAthleteId ? current.state.totalXp : 0,
        }));
      }
    })();

    inFlightRef.current = { key: targetIdentityKey, request };
    try {
      await request;
    } finally {
      if (activeAthleteRef.current === targetAthleteId) {
        lastClaimCompletedAtRef.current = Date.now();
      }
      if (inFlightRef.current?.request === request) {
        inFlightRef.current = null;
      }
    }
  }, [accessToken, applyResult, athleteId, identityKey]);

  useEffect(() => {
    if (!athleteId || !accessToken) {
      inFlightRef.current = null;
      return;
    }
    void claimDaily({ respectCooldown: true });

    const handleFocus = () => void claimDaily({ respectCooldown: true });
    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        void claimDaily({ respectCooldown: true });
      }
    };

    window.addEventListener("focus", handleFocus);
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      window.removeEventListener("focus", handleFocus);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [accessToken, athleteId, claimDaily]);

  const refresh = useCallback(
    () => claimDaily({ respectCooldown: false }),
    [claimDaily],
  );

  const visibleView =
    view.athleteId === (athleteId || null)
      ? view
      : { ...initialViewState(), athleteId: athleteId || null, isHydrated: !athleteId };

  return (
    <XpContext.Provider
      value={{
        state: visibleView.state,
        isHydrated: visibleView.isHydrated,
        dailyRewardStatus: visibleView.dailyRewardStatus,
        isNewAward: visibleView.isNewAward,
        isNewDailyAward: visibleView.isNewDailyAward,
        previousTotalXp: visibleView.previousTotalXp,
        refresh,
      }}
    >
      {children}
    </XpContext.Provider>
  );
}

export function useXp() {
  const context = useContext(XpContext);
  if (!context) {
    throw new Error("useXp must be used within XpProvider.");
  }
  return context;
}
