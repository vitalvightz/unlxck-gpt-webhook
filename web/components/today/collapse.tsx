"use client";

import { useEffect, useState, type CSSProperties, type ReactNode } from "react";

import { prefersReducedMotion } from "@/lib/reduced-motion";

/** Matches today-collapse-out in globals.css. */
export const COLLAPSE_EXIT_MS = 240;

type Phase = "open" | "entering" | "leaving" | "closed";

/**
 * Opens and closes a section by easing its height, so whatever sits below it
 * slides instead of snapping. What was shown stays on screen while it closes,
 * even if the caller has already dropped it. Shown on first render without
 * animating, so the page does not unfold on load.
 *
 * `gap` is the parent's grid gap (any CSS length): it eases away with the section so the
 * last few pixels do not snap when it unmounts.
 */
export function Collapse({ show, gap = "0px", children }: { show: boolean; gap?: string; children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>(show ? "open" : "closed");
  const [wasShown, setWasShown] = useState(show);
  const [heldChildren, setHeldChildren] = useState<ReactNode>(show ? children : null);

  // Derive the phase from `show` during render rather than in an effect, so
  // the first frame after a change already carries the right state.
  if (show !== wasShown) {
    setWasShown(show);
    setPhase(show ? (prefersReducedMotion() ? "open" : "entering") : prefersReducedMotion() ? "closed" : "leaving");
  }
  if (show && children !== heldChildren) {
    setHeldChildren(children);
  }

  useEffect(() => {
    if (phase !== "leaving") return;
    const timer = window.setTimeout(() => setPhase("closed"), COLLAPSE_EXIT_MS);
    return () => window.clearTimeout(timer);
  }, [phase]);

  if (phase === "closed") return null;
  return (
    <div
      className="today-collapse"
      data-phase={phase}
      // Closing content is only a fading picture: nothing in it is live.
      inert={phase === "leaving" || undefined}
      aria-hidden={phase === "leaving" || undefined}
      style={{ "--today-collapse-gap": gap } as CSSProperties}
      onAnimationEnd={(event) => {
        if (event.target === event.currentTarget && phase === "entering") setPhase("open");
      }}
    >
      <div className="today-collapse-inner">{show ? children : heldChildren}</div>
    </div>
  );
}
