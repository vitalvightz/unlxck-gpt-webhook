"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";

interface WhyTooltipProps {
  title: string;
  body: ReactNode;
  triggerLabel?: string;
  ariaLabel?: string;
}

export function WhyTooltip({
  title,
  body,
  triggerLabel = "Why?",
  ariaLabel,
}: WhyTooltipProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLSpanElement | null>(null);
  const tooltipId = useId();

  useEffect(() => {
    if (!open) {
      return;
    }

    const handlePointerDown = (event: PointerEvent) => {
      if (!containerRef.current) {
        return;
      }
      if (event.target instanceof Node && containerRef.current.contains(event.target)) {
        return;
      }
      setOpen(false);
    };

    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open]);

  return (
    <span
      ref={containerRef}
      className="why-tooltip"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        className="why-tooltip-trigger"
        aria-expanded={open}
        aria-describedby={open ? tooltipId : undefined}
        aria-label={ariaLabel ?? `Why this changed: ${title}`}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          setOpen((current) => !current);
        }}
      >
        {triggerLabel}
      </button>
      {open ? (
        <span id={tooltipId} role="tooltip" className="why-tooltip-bubble">
          <span className="why-tooltip-title">{title}</span>
          <p className="why-tooltip-body">{body}</p>
        </span>
      ) : null}
    </span>
  );
}
