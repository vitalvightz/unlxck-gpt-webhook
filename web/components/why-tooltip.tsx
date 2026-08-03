"use client";

import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

/** useLayoutEffect measures the bubble before paint, but React warns when it is
 * used during SSR — and this component IS server-rendered (closed, so the effect
 * has nothing to do). Fall back to useEffect on the server. */
const useMeasureEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

interface WhyTooltipProps {
  title: string;
  body: ReactNode;
  triggerLabel?: string;
  ariaLabel?: string;
  /** Extra class on the wrapper, for callers that need a smaller trigger
   * (e.g. the glossary "?" that sits beside a 0.68rem stat label). */
  className?: string;
}

/** Gap between the trigger and the bubble. */
const BUBBLE_GAP = 8;
/** Minimum distance the bubble keeps from every viewport edge. */
const VIEWPORT_MARGIN = 8;
/** Distance from the bubble's edge that the arrow will not pass. */
const ARROW_INSET = 14;
/** Hover grace period so the pointer can cross the gap into the bubble. */
const CLOSE_DELAY_MS = 120;

type BubblePosition = {
  top: number;
  left: number;
  placement: "above" | "below";
  /** Arrow offset from the bubble's left edge, so it keeps pointing at the
   * trigger even once the bubble has been clamped away from it. */
  arrowLeft: number;
};

/**
 * A "?" (or "Why?") affordance whose bubble is positioned against the VIEWPORT,
 * not its parent.
 *
 * The bubble used to be an absolutely-positioned child, which meant any ancestor
 * with `overflow: hidden` (the plan accordion, the week rail) clipped it, and a
 * trigger near a screen edge pushed it off-screen. It now renders in a portal on
 * <body> with fixed coordinates measured from the trigger, flipping below when
 * there is no room above and clamping to the viewport on both axes — so wherever
 * the "?" appears, the explanation is fully readable.
 */
export function WhyTooltip({
  title,
  body,
  triggerLabel = "Why?",
  ariaLabel,
  className,
}: WhyTooltipProps) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<BubblePosition | null>(null);
  const containerRef = useRef<HTMLSpanElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const bubbleRef = useRef<HTMLSpanElement | null>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // True once the athlete has deliberately clicked/tapped the trigger open, as
  // opposed to merely hovering over it. See the click handler.
  const pinned = useRef(false);
  const tooltipId = useId();

  const cancelClose = useCallback(() => {
    if (closeTimer.current !== null) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  }, []);

  const openNow = useCallback(() => {
    cancelClose();
    setOpen(true);
  }, [cancelClose]);

  // Clearing the position on the way out means the next open always starts with
  // the hidden measuring pass instead of flashing at the previous coordinates.
  const closeNow = useCallback(() => {
    cancelClose();
    pinned.current = false;
    setOpen(false);
    setPosition(null);
  }, [cancelClose]);

  /** Leaves the bubble open briefly so the pointer can travel into it. A pinned
   * bubble ignores this — it was opened on purpose and stays until dismissed. */
  const closeSoon = useCallback(() => {
    if (pinned.current) {
      return;
    }
    cancelClose();
    closeTimer.current = setTimeout(() => {
      closeTimer.current = null;
      setOpen(false);
      setPosition(null);
    }, CLOSE_DELAY_MS);
  }, [cancelClose]);

  useEffect(() => cancelClose, [cancelClose]);

  const updatePosition = useCallback(() => {
    const trigger = triggerRef.current;
    const bubble = bubbleRef.current;
    if (!trigger || !bubble) {
      return;
    }
    const triggerRect = trigger.getBoundingClientRect();
    const bubbleRect = bubble.getBoundingClientRect();
    // clientWidth/Height is the layout viewport (it excludes the scrollbar,
    // which innerWidth does not), but it reads 0 before the document has a
    // layout box — fall back rather than clamp everything into the corner.
    const viewportWidth = document.documentElement.clientWidth || window.innerWidth;
    const viewportHeight = document.documentElement.clientHeight || window.innerHeight;
    const { width, height } = bubbleRect;

    // Prefer above (the historical look); flip below when the bubble would not
    // fit there and there is more room underneath.
    const roomAbove = triggerRect.top - VIEWPORT_MARGIN - BUBBLE_GAP;
    const roomBelow = viewportHeight - triggerRect.bottom - VIEWPORT_MARGIN - BUBBLE_GAP;
    const placement: "above" | "below" =
      roomAbove >= height || roomAbove >= roomBelow ? "above" : "below";

    const rawTop =
      placement === "above"
        ? triggerRect.top - BUBBLE_GAP - height
        : triggerRect.bottom + BUBBLE_GAP;
    // Clamp last so a bubble taller than the space available still shows its top
    // edge rather than scrolling off the screen.
    const maxTop = Math.max(VIEWPORT_MARGIN, viewportHeight - height - VIEWPORT_MARGIN);
    const top = Math.min(Math.max(rawTop, VIEWPORT_MARGIN), maxTop);

    const triggerCenter = triggerRect.left + triggerRect.width / 2;
    const maxLeft = Math.max(VIEWPORT_MARGIN, viewportWidth - width - VIEWPORT_MARGIN);
    const left = Math.min(Math.max(triggerCenter - width / 2, VIEWPORT_MARGIN), maxLeft);

    const arrowLeft = Math.min(
      Math.max(triggerCenter - left, ARROW_INSET),
      Math.max(ARROW_INSET, width - ARROW_INSET),
    );

    setPosition((current) =>
      current &&
      current.top === top &&
      current.left === left &&
      current.placement === placement &&
      current.arrowLeft === arrowLeft
        ? current
        : { top, left, placement, arrowLeft },
    );
  }, []);

  // Measure once the bubble is in the DOM, then track anything that moves the
  // trigger under it. Scroll is captured so inner scrollers count too.
  useMeasureEffect(() => {
    if (!open) {
      return;
    }
    updatePosition();
    window.addEventListener("scroll", updatePosition, true);
    window.addEventListener("resize", updatePosition);
    return () => {
      window.removeEventListener("scroll", updatePosition, true);
      window.removeEventListener("resize", updatePosition);
    };
  }, [open, updatePosition]);

  useEffect(() => {
    if (!open) {
      return;
    }

    const handlePointerDown = (event: PointerEvent) => {
      if (!(event.target instanceof Node)) {
        return;
      }
      // The bubble is portalled out of the container, so it needs its own
      // inside-check or tapping a link in the copy would dismiss it.
      if (
        containerRef.current?.contains(event.target) ||
        bubbleRef.current?.contains(event.target)
      ) {
        return;
      }
      closeNow();
    };

    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeNow();
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open, closeNow]);

  // `open` is always false during SSR, so gating the portal on it is enough to
  // keep <body> out of the server render without a mounted flag.
  const bubble =
    open && typeof document !== "undefined"
      ? createPortal(
          <span
            ref={bubbleRef}
            id={tooltipId}
            role="tooltip"
            className="why-tooltip-bubble"
            data-placement={position?.placement ?? "above"}
            style={{
              top: position ? `${position.top}px` : 0,
              left: position ? `${position.left}px` : 0,
              // Hidden for the measuring pass only, so the bubble never flashes
              // at the top-left corner before it is placed.
              visibility: position ? undefined : "hidden",
              ["--why-tooltip-arrow-left" as string]: `${position?.arrowLeft ?? 0}px`,
            }}
            onMouseEnter={openNow}
            onMouseLeave={closeSoon}
          >
            <span className="why-tooltip-title">{title}</span>
            <p className="why-tooltip-body">{body}</p>
          </span>,
          document.body,
        )
      : null;

  return (
    <span
      ref={containerRef}
      className={className ? `why-tooltip ${className}` : "why-tooltip"}
      onMouseEnter={openNow}
      onMouseLeave={closeSoon}
    >
      <button
        ref={triggerRef}
        type="button"
        className="why-tooltip-trigger"
        aria-expanded={open}
        aria-describedby={open ? tooltipId : undefined}
        aria-label={ariaLabel ?? `Why this changed: ${title}`}
        onFocus={openNow}
        // Blur is an unambiguous "focus has left" signal, so it dismisses even a
        // pinned bubble — otherwise tabbing away would strand it on screen.
        onBlur={closeNow}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          // A tap on a touch screen fires synthesized mouseover FIRST, so by the
          // time the click lands the bubble is already open from "hover". A plain
          // toggle therefore closed it again and the tooltip could never be read
          // on a phone at all. Only a click on an already-PINNED bubble closes:
          // the first click always pins whatever hover opened.
          if (pinned.current) {
            closeNow();
            return;
          }
          pinned.current = true;
          openNow();
        }}
      >
        {triggerLabel}
      </button>
      {bubble}
    </span>
  );
}
