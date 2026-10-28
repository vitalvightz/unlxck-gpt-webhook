"use client";

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { prefersReducedMotion } from "@/lib/reduced-motion";

/** Match today-collapse-in / today-collapse-out in globals.css. */
export const COLLAPSE_ENTER_MS = 340;
export const COLLAPSE_EXIT_MS = 280;
const EASE = "cubic-bezier(0.37, 0, 0.63, 1)";
const SLIDING = '.today-collapse[data-phase="entering"], .today-collapse[data-phase="leaving"]';

/** The nearest sibling that keeps its size: a sliding section has none to lend. */
function steadySibling(element: Element, direction: "previousElementSibling" | "nextElementSibling") {
  let sibling = element[direction];
  while (sibling?.matches(SLIDING)) sibling = sibling[direction];
  return sibling as HTMLElement | null;
}

type Phase = "open" | "entering" | "leaving" | "closed";

/**
 * Opens and closes a section by easing its height, so whatever sits below it
 * slides instead of snapping. What was shown stays on screen while it closes,
 * even if the caller has already dropped it. Shown on first render without
 * animating, so the page does not unfold on load.
 */
export function Collapse({ show, children }: { show: boolean; children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>(show ? "open" : "closed");
  const [wasShown, setWasShown] = useState(show);
  const [heldChildren, setHeldChildren] = useState<ReactNode>(show ? children : null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const gapAnimation = useRef<Animation | null>(null);

  // Derive the phase from `show` during render rather than in an effect, so
  // the first frame after a change already carries the right state.
  if (show !== wasShown) {
    setWasShown(show);
    setPhase(show ? (prefersReducedMotion() ? "open" : "entering") : prefersReducedMotion() ? "closed" : "leaving");
  }
  if (show && children !== heldChildren) {
    setHeldChildren(children);
  }

  // In a grid parent, the section's own track can never be smaller than
  // nothing, so the parent's gap would appear in one frame on open and vanish
  // in one on close. A neighbour has height to spare: ease the gap through
  // its margin instead, and drop that in the same commit the section goes.
  useLayoutEffect(() => {
    if (phase !== "entering" && phase !== "leaving") {
      gapAnimation.current?.cancel();
      gapAnimation.current = null;
      return;
    }
    const wrapper = wrapperRef.current;
    const parent = wrapper?.parentElement;
    if (!wrapper || !parent) return;
    const gap = Number.parseFloat(getComputedStyle(parent).rowGap) || 0;
    const before = steadySibling(wrapper, "previousElementSibling");
    const neighbour = before ?? steadySibling(wrapper, "nextElementSibling");
    if (!gap || !neighbour || typeof neighbour.animate !== "function") return;
    const side = before ? "marginBottom" : "marginTop";
    // Added on top of the neighbour's own margin, so two sections sliding
    // beside the same neighbour each take their own gap.
    const absorbed = { [side]: `${-gap}px` };
    const resting = { [side]: "0px" };
    gapAnimation.current?.cancel();
    gapAnimation.current = phase === "entering"
      ? neighbour.animate([absorbed, resting], { duration: COLLAPSE_ENTER_MS, easing: EASE, composite: "add" })
      : neighbour.animate([resting, absorbed], { duration: COLLAPSE_EXIT_MS, easing: EASE, composite: "add", fill: "forwards" });
    // A finished, held animation is dropped by the browser once another one on
    // the same margin finishes after it, even though both add. With two
    // sections closing beside one neighbour, that put a gap back for a frame.
    if (phase === "leaving") gapAnimation.current.persist?.();
  }, [phase]);

  useEffect(() => () => gapAnimation.current?.cancel(), []);

  // Normally the exit animation's end unmounts the section (below). The timer
  // only covers a browser that never fires it; ending early on a busy phone
  // would cut the last few pixels into a snap.
  useEffect(() => {
    if (phase !== "leaving") return;
    const timer = window.setTimeout(() => setPhase("closed"), COLLAPSE_EXIT_MS + 150);
    return () => window.clearTimeout(timer);
  }, [phase]);

  if (phase === "closed") return null;
  return (
    <div
      ref={wrapperRef}
      className="today-collapse"
      data-phase={phase}
      // Closing content is only a fading picture: nothing in it is live.
      inert={phase === "leaving" || undefined}
      aria-hidden={phase === "leaving" || undefined}
      onAnimationEnd={(event) => {
        if (event.target !== event.currentTarget) return;
        if (phase === "entering") setPhase("open");
        else if (phase === "leaving") setPhase("closed");
      }}
    >
      <div className="today-collapse-inner">{show ? children : heldChildren}</div>
    </div>
  );
}
