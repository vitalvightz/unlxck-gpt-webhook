"use client";

import { useEffect, useLayoutEffect, useRef, type ReactNode } from "react";

import { prefersReducedMotion } from "@/lib/reduced-motion";

const RESIZE_MS = 260;
const SWAP_MS = 320;
const EASE = "cubic-bezier(0.16, 1, 0.3, 1)";

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

    // The observer runs after layout but before paint, so pinning the old
    // height here means the new height is never seen as a jump.
    const observer = new ResizeObserver(() => {
      const nextHeight = inner.offsetHeight;
      if (nextHeight === lastHeight) return;
      if (prefersReducedMotion()) {
        lastHeight = nextHeight;
        return;
      }
      // Mid-glide, start from where the box is now, not where it was heading.
      const fromHeight = outer.style.height ? outer.getBoundingClientRect().height : lastHeight;
      lastHeight = nextHeight;
      outer.style.transition = "none";
      outer.style.overflow = "hidden";
      outer.style.height = `${fromHeight}px`;
      void outer.offsetHeight;
      outer.style.transition = `height ${RESIZE_MS}ms ${EASE}`;
      outer.style.height = `${nextHeight}px`;
      window.clearTimeout(settleTimer);
      settleTimer = window.setTimeout(() => {
        outer.style.transition = "";
        outer.style.overflow = "";
        outer.style.height = "";
      }, RESIZE_MS + 20);
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
      { duration: prefersReducedMotion() ? 200 : SWAP_MS, easing: EASE },
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
