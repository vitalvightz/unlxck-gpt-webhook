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
  const inFlightRef = useRef<{ key: string; request: Promise<void> } | null>(null);

  useEffect(() => {
    activeIdentityRef.current = identityKey;
  }, [identityKey]);

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

  const claimDaily = useCallback(async () => {
    if (!athleteId || !accessToken || !identityKey) {
      return;
    }

    if (inFlightRef.current?.key === identityKey) {
      await inFlightRef.current.request;
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
    void claimDaily();

    const handleFocus = () => void claimDaily();
    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        void claimDaily();
      }
    };

    window.addEventListener("focus", handleFocus);
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      window.removeEventListener("focus", handleFocus);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [accessToken, athleteId, claimDaily]);

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
        refresh: claimDaily,
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
