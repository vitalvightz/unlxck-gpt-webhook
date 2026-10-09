"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { lockOverlayScroll } from "@/lib/overlay-scroll-lock";

/** Injury details stay off the daily card; reuse the app's iOS scroll lock.
 * `variant="screen"` fills the viewport for a full screen (Today's session
 * preview). Sheets stack: only the topmost one answers Escape and Tab. */
export function InjuryDetailSheet({ title, children, onClose, busy = false, variant = "sheet", closeLabel = "Close" }: {
  title: string; children: ReactNode; onClose: () => void; busy?: boolean;
  variant?: "sheet" | "screen"; closeLabel?: string;
}) {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const state = useRef({ busy, onClose });
  useEffect(() => { state.current = { busy, onClose }; }, [busy, onClose]);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const release = lockOverlayScroll();
    panel.current?.focus({ preventScroll: true });
    function keydown(event: KeyboardEvent) {
      const dialogs = document.querySelectorAll('[role="dialog"][aria-modal="true"]');
      if (dialogs[dialogs.length - 1] !== panel.current) return;
      if (event.key === "Escape") {
        event.preventDefault();
        if (!state.current.busy) state.current.onClose();
      }
      if (event.key !== "Tab") return;
      const controls = Array.from(panel.current?.querySelectorAll<HTMLElement>(
        'button:not(:disabled), select:not(:disabled), input:not(:disabled), summary, a[href], [tabindex="0"]',
      ) ?? []).filter(control => {
        const details = control.closest("details");
        return !details || details.open || control.tagName === "SUMMARY";
      });
      const first = controls[0], last = controls.at(-1);
      if (!first) { event.preventDefault(); panel.current?.focus(); }
      else if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) {
        event.preventDefault(); last?.focus();
      } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === panel.current)) {
        event.preventDefault(); first.focus();
      }
    }
    document.addEventListener("keydown", keydown);
    return () => { document.removeEventListener("keydown", keydown); release(); previous?.focus({ preventScroll: true }); };
  }, []);
  if (typeof document === "undefined") return null;
  return createPortal(<div className="injury-sheet-backdrop" data-variant={variant} onClick={() => { if (!busy) onClose(); }}>
    <div className="injury-sheet" data-variant={variant} ref={panel} role="dialog" aria-modal="true" aria-labelledby={titleId}
      aria-busy={busy} tabIndex={-1} onClick={event => event.stopPropagation()}>
      <div className="injury-sheet-header"><h2 id={titleId}>{title}</h2>
        <button type="button" className="injury-sheet-close" aria-label={closeLabel} disabled={busy} onClick={onClose}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d={variant === "screen" ? "m15 5-7 7 7 7" : "m6 6 12 12M6 18 18 6"} /></svg>
        </button>
      </div>
      {children}
    </div>
  </div>, document.body);
}

export function InjuryChevron() {
  return <svg className="injury-chevron" viewBox="0 0 24 24" aria-hidden="true"><path d="m9 5 7 7-7 7" /></svg>;
}
