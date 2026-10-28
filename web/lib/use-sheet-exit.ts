"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { prefersReducedMotion } from "@/lib/reduced-motion";

/** Matches the sheet-out / backdrop-out animations (200ms) in the sheet styles. */
export const SHEET_EXIT_MS = 200;

/**
 * Lets a sheet play its closing animation before it is removed. `close`
 * marks the sheet as closing (render `data-closing={closing || undefined}` on
 * it), then calls `dismiss` once the animation is done. Without this a sheet
 * and its backdrop vanished in a single frame.
 *
 * If the parent keeps the sheet after `dismiss` (it asked to confirm, say),
 * the sheet simply shows again.
 */
export function useSheetExit<Args extends unknown[]>(dismiss: (...args: Args) => void) {
  const [closing, setClosing] = useState(false);
  const timer = useRef<number | null>(null);
  const latest = useRef(dismiss);

  useEffect(() => {
    latest.current = dismiss;
  });

  useEffect(() => () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
  }, []);

  const close = useCallback((...args: Args) => {
    if (prefersReducedMotion()) {
      latest.current(...args);
      return;
    }
    // Already on its way out: a second tap must not dismiss twice.
    if (timer.current !== null) return;
    setClosing(true);
    timer.current = window.setTimeout(() => {
      timer.current = null;
      latest.current(...args);
      setClosing(false);
    }, SHEET_EXIT_MS);
  }, []);

  return { closing, close };
}
