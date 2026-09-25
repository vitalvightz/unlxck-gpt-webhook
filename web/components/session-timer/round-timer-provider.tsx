"use client";

import { createContext, useContext, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";

import { SessionTimer } from "@/components/session-timer/session-timer";
import { clearSavedRun, hasSavedRun } from "@/components/session-timer/use-session-timer";
import { resolveTrainingDay, toISODate } from "@/lib/camp-map";
import { timerAudio } from "@/lib/session-timer/audio";
import { freeRoundsItem } from "@/lib/session-timer/contact";

/** One plain round timer for the whole app: not tied to a plan, day or page. */
export const ROUND_TIMER_STORAGE_KEY = "unlxck.session-timer.free";
/** Today's saved planned-session and contact runs: `<prefix><plan>:…:<training day>`. */
export const SESSION_RUN_KEY_PREFIX = "unlxck.session-timer.run:";
export const CONTACT_RUN_KEY_PREFIX = "unlxck.session-timer.contact:";

/**
 * Is a planned-session or contact run saved for the current training day?
 * Today brings that run back as its mini bar, so the round timer must not
 * start alongside it: only one timer is ever on screen. Runs saved on an
 * earlier day are never restored by Today, so they never block.
 */
export function hasSavedTodayRun(now: Date = new Date()): boolean {
  try {
    const suffix = `:${toISODate(resolveTrainingDay(now))}`;
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index);
      if (
        key &&
        (key.startsWith(SESSION_RUN_KEY_PREFIX) || key.startsWith(CONTACT_RUN_KEY_PREFIX)) &&
        key.endsWith(suffix)
      ) {
        return true;
      }
    }
  } catch {
    // No storage, nothing saved.
  }
  return false;
}

/**
 * Today is the authority on which of its runs it can resume. It calls this
 * with the runs it can resume, and every other planned-session or contact run
 * saved for that training day is dropped: a run left behind by a plan or
 * session that changed, or a session already logged, would otherwise block
 * the round timer with nothing on Today to resume.
 */
export function pruneSavedTodayRuns(trainingDay: string, resumable: readonly string[]): void {
  try {
    const suffix = `:${trainingDay}`;
    const stale: string[] = [];
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index);
      if (
        key &&
        (key.startsWith(SESSION_RUN_KEY_PREFIX) || key.startsWith(CONTACT_RUN_KEY_PREFIX)) &&
        key.endsWith(suffix) &&
        !resumable.includes(key)
      ) {
        stale.push(key);
      }
    }
    for (const key of stale) window.localStorage.removeItem(key);
  } catch {
    // No storage, nothing saved.
  }
}

/** Re-read on every render of the caller, client only (server says no). */
export function useSavedTodayRun(): boolean {
  return useSyncExternalStore(subscribeToNothing, () => hasSavedTodayRun(), () => false);
}

type RoundTimerContextValue = {
  /** The round timer is on screen, full size or as its mini bar. */
  shown: boolean;
  /**
   * Open the round timer. Call inside the tap, so its audio can unlock. Does
   * nothing while Today has a session or contact run saved: resume that one.
   */
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
        if (shownMode === null && hasSavedTodayRun()) return;
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
