"use client";

import { useEffect, useLayoutEffect, useRef, type ReactNode } from "react";

import { prefersReducedMotion } from "@/lib/reduced-motion";

const RESIZE_MS = 340;
const SWAP_MS = 320;
// Sine in and out, the same as Collapse: a front-loaded curve moved most of
// the way in one frame on a phone, which read as a jolt rather than a glide.
const RESIZE_EASE = "cubic-bezier(0.37, 0, 0.63, 1)";
const SWAP_EASE = "cubic-bezier(0.22, 0.61, 0.36, 1)";
/** A Collapse inside is already easing its own height. */
const SLIDING_CHILD = '.today-collapse[data-phase="entering"], .today-collapse[data-phase="leaving"]';

/**
 * Glides its height when the content grows or shrinks, instead of snapping
 * everything below it. When `swapKey` changes (a different session took the
 * card) the content also fades and rises in, without remounting it.
 */
export function AutoHeight({
  children,
  className,
  swapKey,
}: {
  children: ReactNode;
  className?: string;
  swapKey?: string;
}) {
  const outerRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const shownKeyRef = useRef(swapKey);

  useLayoutEffect(() => {
    const outer = outerRef.current;
    const inner = innerRef.current;
    if (!outer || !inner || typeof ResizeObserver === "undefined") return;
    let lastHeight = inner.offsetHeight;
    let settleTimer: number | undefined;
    let childWasSliding = false;

    const release = () => {
      window.clearTimeout(settleTimer);
      outer.style.transition = "";
      outer.style.overflow = "";
      outer.style.height = "";
    };

    const glideTo = (nextHeight: number) => {
      // Mid-glide, start from where the box is now, not where it was heading.
      const fromHeight = outer.style.height ? outer.getBoundingClientRect().height : lastHeight;
      lastHeight = nextHeight;
      outer.style.transition = "none";
      outer.style.overflow = "hidden";
      outer.style.height = `${fromHeight}px`;
      void outer.offsetHeight;
      outer.style.transition = `height ${RESIZE_MS}ms ${RESIZE_EASE}`;
      outer.style.height = `${nextHeight}px`;
      window.clearTimeout(settleTimer);
      settleTimer = window.setTimeout(() => {
        // Content that kept changing during the glide gets one more glide,
        // rather than a snap when the height is handed back.
        const settled = inner.offsetHeight;
        if (Math.abs(settled - lastHeight) > 1 && !prefersReducedMotion()) glideTo(settled);
        else release();
      }, RESIZE_MS + 20);
    };

    // The observer runs after layout but before paint, so pinning the old
    // height here means the new height is never seen as a jump.
    const observer = new ResizeObserver(() => {
      const nextHeight = inner.offsetHeight;
      if (nextHeight === lastHeight) return;
      // An inner Collapse grows a little every frame; chasing it restarted
      // this glide every frame and stuttered. It eases itself: stand aside,
      // including for the frame it leaves, which is the end of its own motion.
      const childSliding = Boolean(inner.querySelector(SLIDING_CHILD));
      if (prefersReducedMotion() || childSliding || childWasSliding) {
        childWasSliding = childSliding;
        lastHeight = nextHeight;
        release();
        return;
      }
      glideTo(nextHeight);
    });
    observer.observe(inner);
    return () => {
      observer.disconnect();
      window.clearTimeout(settleTimer);
    };
  }, []);

  useEffect(() => {
    if (shownKeyRef.current === swapKey) return;
    shownKeyRef.current = swapKey;
    const inner = innerRef.current;
    if (!inner || typeof inner.animate !== "function") return;
    inner.animate(
      prefersReducedMotion()
        ? [{ opacity: 0 }, { opacity: 1 }]
        : [
            { opacity: 0, transform: "translateY(8px)" },
            { opacity: 1, transform: "none" },
          ],
      { duration: prefersReducedMotion() ? 200 : SWAP_MS, easing: SWAP_EASE },
    );
  }, [swapKey]);

  return (
    <div ref={outerRef} className={className ? `today-auto-height ${className}` : "today-auto-height"}>
      <div ref={innerRef} className="today-auto-height-inner">
        {children}
      </div>
    </div>
  );
}
