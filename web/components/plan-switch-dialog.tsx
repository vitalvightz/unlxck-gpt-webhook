"use client";

import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

import type { ActivePlanOverlapAction } from "@/lib/plan-active";
import { formatPlanFightDate } from "@/lib/plan-format";

export function PlanSwitchDialog({
  plan,
  isPending,
  onConfirm,
  onCancel,
  errorMessage,
}: {
  plan: { plan_name?: string | null; fight_date?: string | null };
  isPending: boolean;
  onConfirm: (action: ActivePlanOverlapAction) => Promise<void>;
  onCancel: () => void;
  errorMessage?: string | null;
}) {
  const [archivePrevious, setArchivePrevious] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const bodyId = useId();
  const pendingRef = useRef(isPending);
  const cancelRef = useRef(onCancel);

  useEffect(() => {
    pendingRef.current = isPending;
    cancelRef.current = onCancel;
  }, [isPending, onCancel]);

  useEffect(() => {
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialogRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        if (!pendingRef.current) cancelRef.current();
      }
      if (event.key !== "Tab") return;
      const controls = Array.from(
        dialogRef.current?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled)") ?? [],
      );
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (!first) {
        event.preventDefault();
        dialogRef.current?.focus();
      } else if (event.shiftKey && (document.activeElement === first || document.activeElement === dialogRef.current)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialogRef.current)) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, []);

  if (typeof document === "undefined") return null;

  const name = plan.plan_name?.trim();
  const hasCustomName = name && name !== plan.fight_date;

  return createPortal(
    <div className="plan-dialog-backdrop" onClick={() => { if (!isPending) onCancel(); }}>
      <div
        ref={dialogRef}
        className="plan-dialog plan-switch-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={bodyId}
        aria-busy={isPending}
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="plan-dialog-header">
          <h2 id={titleId} className="plan-dialog-title">Switch active plan?</h2>
          <p className="plan-switch-target">
            <strong>{hasCustomName ? name : plan.fight_date ? "Fight camp" : "Performance block"}</strong>
            <span>{plan.fight_date ? `Fight · ${formatPlanFightDate(plan.fight_date)}` : "No fight date"}</span>
          </p>
        </div>
        <p id={bodyId} className="muted">
          This plan will become your active training plan. Your previous plan stays saved unless you archive it.
        </p>
        <label className="plan-switch-archive">
          <input type="checkbox" checked={archivePrevious} disabled={isPending} onChange={(event) => setArchivePrevious(event.target.checked)} />
          <span>Archive previous plan</span>
        </label>
        {errorMessage ? <p className="error-banner" role="alert">{errorMessage}</p> : null}
        <div className="plan-switch-actions">
          <button type="button" className="secondary-button plan-switch-confirm" disabled={isPending} onClick={() => void onConfirm(archivePrevious ? "replace" : "pause")}>
            {isPending ? "Switching…" : "Switch plan"}
          </button>
          <button type="button" className="ghost-button plan-switch-cancel" disabled={isPending} onClick={onCancel}>Cancel</button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
