"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  loadSoundSettings,
  saveSoundSettings,
  timerAudio,
  type TimerSound,
  type TimerSoundSettings,
} from "@/lib/session-timer/audio";
import {
  advance,
  calloutForEvents,
  createTimerState,
  crossedCues,
  cueRemainingMs,
  soundForEvents,
  viewAt,
  type TimerEvent,
  type TimerState,
  type TimerStep,
} from "@/lib/session-timer/engine";
import type { TimerItem } from "@/lib/session-timer/plan";

// 2: ranged rest stays in rest until its maximum (readyAt replaced windowEndsAt).
const RUN_VERSION = 2;
const TICK_MS = 100;
/** The fight-ring bells still ring while the timer is minimised. */
const MINIMIZED_SOUNDS: ReadonlySet<TimerSound> = new Set(["bell", "triple_bell", "finish"]);

type SavedRun = { version: number; key: string; itemIds: string[]; state: TimerState };

function itemIds(items: TimerItem[]): string[] {
  return items.map((item) => `${item.kind}:${item.id}`);
}

/** The saved run for this session, if it still matches the plan's items. */
export function loadSavedRun(storageKey: string, items: TimerItem[]): TimerState | null {
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return null;
    const saved = JSON.parse(raw) as SavedRun;
    const ids = itemIds(items);
    if (
      saved?.version !== RUN_VERSION ||
      saved.key !== storageKey ||
      !Array.isArray(saved.itemIds) ||
      saved.itemIds.join("|") !== ids.join("|")
    ) {
      return null;
    }
    return saved.state;
  } catch {
    return null;
  }
}

export function hasSavedRun(storageKey: string): boolean {
  try {
    return Boolean(window.localStorage.getItem(storageKey));
  } catch {
    return false;
  }
}

export function clearSavedRun(storageKey: string): void {
  try {
    window.localStorage.removeItem(storageKey);
  } catch {
    // Nothing to clear.
  }
}

function saveRun(storageKey: string, state: TimerState): void {
  try {
    const run: SavedRun = {
      version: RUN_VERSION,
      key: storageKey,
      itemIds: itemIds(state.items),
      state,
    };
    window.localStorage.setItem(storageKey, JSON.stringify(run));
  } catch {
    // Resume is a convenience; the live timer does not depend on storage.
  }
}

type WakeLockSentinelLike = { release: () => Promise<void> };
type WakeLockNavigator = Navigator & {
  wakeLock?: { request: (type: "screen") => Promise<WakeLockSentinelLike> };
};

/** Keep the screen on while `active`, re-acquiring after the tab returns. */
function useWakeLock(active: boolean): void {
  useEffect(() => {
    if (!active) return;
    const nav = navigator as WakeLockNavigator;
    if (!nav.wakeLock) return;
    let sentinel: WakeLockSentinelLike | null = null;
    let cancelled = false;
    const acquire = () => {
      if (document.visibilityState !== "visible") return;
      nav.wakeLock
        ?.request("screen")
        .then((lock) => {
          if (cancelled) {
            void lock.release();
          } else {
            sentinel = lock;
          }
        })
        .catch(() => {
          // Denied (battery saver, unsupported): the timer still runs.
        });
    };
    acquire();
    document.addEventListener("visibilitychange", acquire);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", acquire);
      void sentinel?.release().catch(() => undefined);
    };
  }, [active]);
}

export type SessionTimerController = {
  state: TimerState;
  now: number;
  settings: TimerSoundSettings;
  setSettings: (settings: TimerSoundSettings) => void;
  /** Apply an engine action that may emit events (plays their sound). */
  run: (action: (state: TimerState, now: number) => TimerStep) => void;
  /** Apply a silent engine update. */
  update: (action: (state: TimerState, now: number) => TimerState) => void;
};

/**
 * Drives the pure timer engine: ticks it, plays sounds for its events and
 * warning cues, keeps the screen awake and saves the run so Resume restores
 * the exact round or set.
 */
export function useSessionTimer({
  items,
  storageKey,
  audible,
}: {
  items: TimerItem[];
  storageKey: string;
  /** False while the timer is minimised: the clock keeps running, and only the round bells ring. */
  audible: boolean;
}): SessionTimerController {
  const [state, setState] = useState<TimerState>(
    () => loadSavedRun(storageKey, items) ?? createTimerState(items),
  );
  const [now, setNow] = useState(() => Date.now());
  const [settings, setSettingsState] = useState<TimerSoundSettings>(() => loadSoundSettings());
  const stateRef = useRef(state);
  const audibleRef = useRef(audible);
  const lastRemainingRef = useRef<number | null>(null);

  useEffect(() => {
    audibleRef.current = audible;
  }, [audible]);

  useEffect(() => {
    timerAudio().configure(settings);
  }, [settings]);

  const announce = useCallback((events: TimerEvent[], next: TimerState) => {
    if (events.length === 0) return;
    const sound = soundForEvents(events);
    // Minimised, the round bells still ring so the athlete hears each round
    // end; beeps, chimes and callouts stay quiet.
    if (!audibleRef.current) {
      if (sound && MINIMIZED_SOUNDS.has(sound)) timerAudio().play(sound);
      return;
    }
    if (sound) timerAudio().play(sound);
    const callout = calloutForEvents(events, next);
    if (callout) timerAudio().say(callout);
  }, []);

  const commit = useCallback(
    (next: TimerState) => {
      stateRef.current = next;
      lastRemainingRef.current = cueRemainingMs(viewAt(next, Date.now()));
      setState(next);
      if (next.phase === "done" && next.endedAt !== null) {
        clearSavedRun(storageKey);
      } else {
        saveRun(storageKey, next);
      }
    },
    [storageKey],
  );

  const run = useCallback(
    (action: (current: TimerState, at: number) => TimerStep) => {
      const at = Date.now();
      const { state: next, events } = action(stateRef.current, at);
      if (next === stateRef.current) return;
      announce(events, next);
      commit(next);
      setNow(at);
    },
    [announce, commit],
  );

  const update = useCallback(
    (action: (current: TimerState, at: number) => TimerState) => {
      const at = Date.now();
      const next = action(stateRef.current, at);
      if (next === stateRef.current) return;
      commit(next);
      setNow(at);
    },
    [commit],
  );

  const running =
    (state.phase === "work" || state.phase === "rest") && state.pausedAt === null;

  useEffect(() => {
    if (!running) return;
    const tick = () => {
      const at = Date.now();
      const current = stateRef.current;
      const { state: next, events } = advance(current, at);
      if (next !== current) {
        announce(events, next);
        commit(next);
      } else if (audibleRef.current) {
        const remaining = cueRemainingMs(viewAt(current, at));
        const cues = crossedCues(current.phase, current.phaseMs, lastRemainingRef.current, remaining);
        lastRemainingRef.current = remaining;
        const audio = timerAudio();
        if (cues.includes("ten_seconds")) audio.play("clapper");
        if (cues.some((cue) => cue.startsWith("count_"))) audio.play("beep");
      } else {
        lastRemainingRef.current = cueRemainingMs(viewAt(current, at));
      }
      setNow(at);
    };
    tick();
    const interval = window.setInterval(tick, TICK_MS);
    // A returning tab catches up at once instead of waiting for the next tick.
    document.addEventListener("visibilitychange", tick);
    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", tick);
    };
  }, [running, announce, commit]);

  useWakeLock(audible && state.phase !== "done");

  const setSettings = useCallback((next: TimerSoundSettings) => {
    setSettingsState(next);
    saveSoundSettings(next);
  }, []);

  return { state, now, settings, setSettings, run, update };
}
