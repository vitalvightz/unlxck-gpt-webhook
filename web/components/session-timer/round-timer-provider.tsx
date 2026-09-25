"use client";

import { createContext, useContext, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";

import { SessionTimer } from "@/components/session-timer/session-timer";
import { clearSavedRun, hasSavedRun } from "@/components/session-timer/use-session-timer";
import { timerAudio } from "@/lib/session-timer/audio";
import { freeRoundsItem } from "@/lib/session-timer/contact";

/** One plain round timer for the whole app: not tied to a plan, day or page. */
export const ROUND_TIMER_STORAGE_KEY = "unlxck.session-timer.free";

type RoundTimerContextValue = {
  /** The round timer is on screen, full size or as its mini bar. */
  shown: boolean;
  /** Open the round timer. Call inside the tap, so its audio can unlock. */
  open: () => void;
};

const RoundTimerContext = createContext<RoundTimerContextValue>({ shown: false, open: () => {} });

export function useRoundTimer(): RoundTimerContextValue {
  return useContext(RoundTimerContext);
}

/** Saved runs only change through this tab's own actions, which re-render. */
function subscribeToNothing() {
  return () => {};
}

/**
 * Hosts the round timer above every page, so it can be started from anywhere
 * and keeps time (minimised to its mini bar) while the athlete moves around
 * the app. A run left going when the app closed comes back as the mini bar.
 */
export function RoundTimerProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<"open" | "minimized" | null>(null);
  // Read from storage on the client only, so server and first client render agree.
  const hasSaved = useSyncExternalStore(
    subscribeToNothing,
    () => hasSavedRun(ROUND_TIMER_STORAGE_KEY),
    () => false,
  );
  const shownMode = mode ?? (hasSaved ? "minimized" : null);
  const items = useMemo(() => [freeRoundsItem()], []);

  const value = useMemo<RoundTimerContextValue>(
    () => ({
      shown: shownMode !== null,
      open: () => {
        // Audio only unlocks inside the tap itself.
        timerAudio().unlock();
        setMode("open");
      },
    }),
    [shownMode],
  );

  const close = () => {
    clearSavedRun(ROUND_TIMER_STORAGE_KEY);
    setMode(null);
  };

  return (
    <RoundTimerContext.Provider value={value}>
      {children}
      {shownMode ? (
        <SessionTimer
          items={items}
          storageKey={ROUND_TIMER_STORAGE_KEY}
          sessionTitle="Round timer"
          visible={shownMode === "open"}
          finishLabel="Done"
          onMinimize={() => setMode("minimized")}
          onExpand={value.open}
          onClose={close}
          onFinish={close}
        />
      ) : null}
    </RoundTimerContext.Provider>
  );
}
