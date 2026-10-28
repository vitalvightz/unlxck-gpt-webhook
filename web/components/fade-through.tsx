"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import { prefersReducedMotion } from "@/lib/reduced-motion";

/** Match fade-through-cover / fade-through-reveal in globals.css. */
const COVER_MS = 120;
const REVEAL_MS = 220;

type Phase = "idle" | "covering" | "covered" | "revealing";

/** Runs `change` behind a quick fade through black. */
export type FadeThrough = (change: () => void) => void;

const FadeThroughContext = createContext<FadeThrough>((change) => change());

/**
 * Full-screen changes (a timer, a visualisation, a preview screen) fade the
 * page to black, swap while it is black, then fade the new screen in, rather
 * than the new screen popping over the old one in a frame.
 *
 * Anything the browser only allows inside the tap itself (unlocking audio)
 * must happen before calling it: the change runs a moment later.
 */
export function FadeThroughProvider({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const queued = useRef<Array<() => void>>([]);
  const busy = useRef(false);
  const swapped = useRef(false);
  const timers = useRef<number[]>([]);
  const frame = useRef<number | null>(null);

  const fadeThrough = useCallback<FadeThrough>((change) => {
    if (prefersReducedMotion()) {
      change();
      return;
    }
    if (busy.current) {
      // Still going dark: swap together. Already revealing: too late to hide it.
      if (swapped.current) change();
      else queued.current.push(change);
      return;
    }
    busy.current = true;
    swapped.current = false;
    queued.current = [change];
    setPhase("covering");
    timers.current.push(window.setTimeout(() => {
      const changes = queued.current;
      queued.current = [];
      swapped.current = true;
      // A change that throws must not leave the screen black.
      changes.forEach((run) => {
        try {
          run();
        } catch (error) {
          window.setTimeout(() => { throw error; });
        }
      });
      setPhase("covered");
      let revealed = false;
      const reveal = () => {
        if (revealed) return;
        revealed = true;
        if (frame.current !== null) window.cancelAnimationFrame(frame.current);
        frame.current = null;
        setPhase("revealing");
        timers.current.push(window.setTimeout(() => {
          busy.current = false;
          setPhase("idle");
        }, REVEAL_MS));
      };
      // Two frames: the new screen commits and paints under the black first.
      frame.current = window.requestAnimationFrame(() => {
        frame.current = window.requestAnimationFrame(reveal);
      });
      // Frames pause in a background tab; never leave the screen black.
      timers.current.push(window.setTimeout(reveal, 250));
    }, COVER_MS));
  }, []);

  useEffect(() => {
    const pending = timers.current;
    return () => {
      pending.forEach((timer) => window.clearTimeout(timer));
      if (frame.current !== null) window.cancelAnimationFrame(frame.current);
    };
  }, []);

  return (
    <FadeThroughContext.Provider value={fadeThrough}>
      {children}
      {phase === "idle" ? null : <div className="fade-through" data-phase={phase} aria-hidden="true" />}
    </FadeThroughContext.Provider>
  );
}

export function useFadeThrough(): FadeThrough {
  return useContext(FadeThroughContext);
}
