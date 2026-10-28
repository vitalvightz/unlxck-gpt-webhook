"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { prefersReducedMotion } from "@/lib/reduced-motion";

/** Match fade-through-cover / fade-through-reveal in globals.css. */
const COVER_MS = 120;
const REVEAL_MS = 220;
/** A navigation that never lands still lifts the black after this long. */
const NAVIGATION_HOLD_MS = 900;

type Phase = "idle" | "covering" | "covered" | "revealing";

/** Runs `change` behind a quick fade through black. */
export type FadeThrough = (change: () => void) => void;

const now: FadeThrough = (change) => change();
const FadeThroughContext = createContext<{ fadeThrough: FadeThrough; fadeFromBlack: FadeThrough; fadeNavigate: FadeThrough }>({
  fadeThrough: now,
  fadeFromBlack: now,
  fadeNavigate: now,
});

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

  /** Lift the black once the new screen has painted under it. */
  const revealSoon = useCallback(() => {
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
  }, []);

  /** Run the changes under full black, then reveal the new screen. */
  const swapAndReveal = useCallback((changes: Array<() => void>) => {
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
    revealSoon();
  }, [revealSoon]);

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
      swapAndReveal(changes);
    }, COVER_MS));
  }, [swapAndReveal]);

  // Moving to another part of the app (signing in, a new plan): go dark, then
  // navigate, and hold the black until the route has actually changed.
  const path = usePathname();
  const query = useSearchParams();
  const pathname = `${path}?${query?.toString() ?? ""}`;
  const pathnameNow = useRef(pathname);
  const leavingPath = useRef<string | null>(null);
  const holdTimer = useRef<number | null>(null);

  const liftAfterNavigation = useCallback(() => {
    leavingPath.current = null;
    if (holdTimer.current !== null) window.clearTimeout(holdTimer.current);
    holdTimer.current = null;
    revealSoon();
  }, [revealSoon]);

  useEffect(() => {
    pathnameNow.current = pathname;
    if (leavingPath.current === null || pathname === leavingPath.current) return;
    // Route arrival can still be the editor's loading shell. Keep the cover
    // until its content commits, with the existing hold timeout as a fallback.
    const ready = () => {
      if (leavingPath.current !== null && !document.querySelector("[data-route-pending]")) liftAfterNavigation();
    };
    const observer = new MutationObserver(ready);
    observer.observe(document.body, { childList: true, subtree: true });
    ready();
    return () => observer.disconnect();
  }, [liftAfterNavigation, pathname]);

  const fadeNavigate = useCallback<FadeThrough>((navigate) => {
    if (prefersReducedMotion() || busy.current) {
      navigate();
      return;
    }
    busy.current = true;
    swapped.current = false;
    setPhase("covering");
    timers.current.push(window.setTimeout(() => {
      swapped.current = true;
      setPhase("covered");
      leavingPath.current = pathnameNow.current;
      holdTimer.current = window.setTimeout(liftAfterNavigation, NAVIGATION_HOLD_MS);
      try {
        navigate();
      } catch (error) {
        liftAfterNavigation();
        throw error;
      }
    }, COVER_MS));
  }, [liftAfterNavigation]);

  // Arriving straight into a full screen (a page that opens its timer): start
  // already black, so the page underneath is never seen, then fade in. Call it
  // before the first paint (a layout effect).
  const fadeFromBlack = useCallback<FadeThrough>((change) => {
    if (prefersReducedMotion() || busy.current) {
      change();
      return;
    }
    busy.current = true;
    swapAndReveal([change]);
  }, [swapAndReveal]);

  useEffect(() => {
    const pending = timers.current;
    const hold = holdTimer;
    return () => {
      if (hold.current !== null) window.clearTimeout(hold.current);
      pending.forEach((timer) => window.clearTimeout(timer));
      if (frame.current !== null) window.cancelAnimationFrame(frame.current);
    };
  }, []);

  const value = useMemo(() => ({ fadeThrough, fadeFromBlack, fadeNavigate }), [fadeThrough, fadeFromBlack, fadeNavigate]);

  return (
    <FadeThroughContext.Provider value={value}>
      {children}
      {phase === "idle" ? null : <div className="fade-through" data-phase={phase} aria-hidden="true" />}
    </FadeThroughContext.Provider>
  );
}

export function useFadeThrough(): FadeThrough {
  return useContext(FadeThroughContext).fadeThrough;
}

/** Fade a full screen in from black, for arriving straight into it. */
export function useFadeFromBlack(): FadeThrough {
  return useContext(FadeThroughContext).fadeFromBlack;
}

/**
 * Navigate behind a fade through black: for moving to another part of the app
 * (signing in, opening a new plan), not for every link. Pass the navigation,
 * e.g. `fadeNavigate(() => router.push(href))`.
 */
export function useFadeNavigate(): FadeThrough {
  return useContext(FadeThroughContext).fadeNavigate;
}
