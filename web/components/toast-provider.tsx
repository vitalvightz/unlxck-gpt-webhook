"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

export type ToastTone = "info" | "success" | "error";

export interface ToastOptions {
  tone?: ToastTone;
  durationMs?: number;
  /** Hold the toast back this long before it may appear. */
  delayMs?: number;
  /** Keys a follow-up toast may name in `merge` to fold into this one. */
  mergeKeys?: readonly string[];
  /**
   * Fold into a recent toast that shares one of `keys` (e.g. "Sparring logged · +25 XP")
   * instead of stacking a second one. Falls back to `message` when nothing matches.
   */
  merge?: {
    suffix: string;
    keys: readonly string[];
  };
  action?: {
    label: string;
    onClick: () => void;
  };
}

interface Toast extends ToastOptions {
  id: number;
  message: string;
  suffix?: string;
  leaving?: boolean;
}

interface PendingToast {
  toast: Toast;
  readyAt: number;
  queuedAt: number;
}

interface ToastContextValue {
  showToast: (message: string, options?: ToastOptions) => number;
  dismissToast: (id: number) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);
const ToastIdleContext = createContext(true);

const DEFAULT_DURATION_MS = 4_500;
/** At most this many toasts on screen; the rest wait their turn. */
const MAX_VISIBLE = 2;
/** Breathing room between one toast appearing and the next. */
const STAGGER_MS = 400;
/** Matches the toast-out animation in globals.css. */
const EXIT_MS = 220;
/** How recent a success toast must be for a follow-up to fold into it. */
const MERGE_WINDOW_MS = 4_000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const idRef = useRef(0);
  const toastsRef = useRef<Toast[]>([]);
  const shownAtRef = useRef<Map<number, number>>(new Map());
  const pendingRef = useRef<PendingToast[]>([]);
  const lastShownAtRef = useRef(Number.NEGATIVE_INFINITY);
  const timersRef = useRef<Map<number, number>>(new Map());
  const exitTimersRef = useRef<Set<number>>(new Set());
  const pumpTimerRef = useRef<number | null>(null);
  const pumpRef = useRef<() => void>(() => {});

  const commit = useCallback((next: Toast[]) => {
    toastsRef.current = next;
    setToasts(next);
  }, []);

  const syncPending = useCallback((next: PendingToast[]) => {
    pendingRef.current = next;
    setPendingCount(next.length);
  }, []);

  const clearDismissTimer = useCallback((id: number) => {
    const timerId = timersRef.current.get(id);
    if (timerId !== undefined) {
      window.clearTimeout(timerId);
      timersRef.current.delete(id);
    }
  }, []);

  const dismissToast = useCallback(
    (id: number) => {
      if (pendingRef.current.some((item) => item.toast.id === id)) {
        syncPending(pendingRef.current.filter((item) => item.toast.id !== id));
        return;
      }
      const target = toastsRef.current.find((toast) => toast.id === id);
      if (!target || target.leaving) return;
      clearDismissTimer(id);
      commit(toastsRef.current.map((toast) => (toast.id === id ? { ...toast, leaving: true } : toast)));
      const exitTimer = window.setTimeout(() => {
        exitTimersRef.current.delete(exitTimer);
        shownAtRef.current.delete(id);
        commit(toastsRef.current.filter((toast) => toast.id !== id));
        pumpRef.current();
      }, EXIT_MS);
      exitTimersRef.current.add(exitTimer);
    },
    [clearDismissTimer, commit, syncPending],
  );

  const armDismissTimer = useCallback(
    (toast: Toast) => {
      clearDismissTimer(toast.id);
      const duration = toast.durationMs ?? DEFAULT_DURATION_MS;
      if (duration > 0) {
        timersRef.current.set(
          toast.id,
          window.setTimeout(() => dismissToast(toast.id), duration),
        );
      }
    },
    [clearDismissTimer, dismissToast],
  );

  /** Fold `suffix` into a recent toast that opted in to one of `keys`, on screen or still queued. */
  const mergeIntoRecent = useCallback(
    ({ suffix, keys }: NonNullable<ToastOptions["merge"]>, now: number): boolean => {
      const canMerge = (toast: Toast) =>
        toast.tone !== "error" &&
        !toast.suffix &&
        !toast.leaving &&
        (toast.mergeKeys ?? []).some((key) => keys.includes(key));
      const visible = [...toastsRef.current]
        .reverse()
        .find((toast) => canMerge(toast) && now - (shownAtRef.current.get(toast.id) ?? 0) <= MERGE_WINDOW_MS);
      if (visible) {
        const merged = { ...visible, suffix };
        commit(toastsRef.current.map((toast) => (toast.id === visible.id ? merged : toast)));
        // Restart the clock so the reward gets its full read time.
        armDismissTimer(merged);
        return true;
      }
      const queued = [...pendingRef.current]
        .reverse()
        .find((item) => canMerge(item.toast) && now - item.queuedAt <= MERGE_WINDOW_MS);
      if (queued) {
        queued.toast = { ...queued.toast, suffix };
        return true;
      }
      return false;
    },
    [armDismissTimer, commit],
  );

  const pump = useCallback(() => {
    if (pumpTimerRef.current !== null) {
      window.clearTimeout(pumpTimerRef.current);
      pumpTimerRef.current = null;
    }
    const now = Date.now();
    let pending = pendingRef.current;

    // Merges never take a slot, so settle every ready one first.
    const stillPending: PendingToast[] = [];
    for (const item of pending) {
      if (item.readyAt <= now && item.toast.merge && mergeIntoRecent(item.toast.merge, now)) continue;
      stillPending.push(item);
    }
    pending = stillPending;

    // Exiting toasts are still on screen, so they hold their slot until removed.
    const onScreen = toastsRef.current.length;
    const ready = pending.filter((item) => item.readyAt <= now);
    // A failure must not wait behind routine confirmations: it goes first and
    // skips the stagger.
    const next = ready.find((item) => item.toast.tone === "error") ?? ready[0];
    const urgent = next?.toast.tone === "error";
    const staggerReadyAt = lastShownAtRef.current + STAGGER_MS;

    if (next && onScreen < MAX_VISIBLE && (urgent || now >= staggerReadyAt)) {
      pending = pending.filter((item) => item !== next);
      lastShownAtRef.current = now;
      shownAtRef.current.set(next.toast.id, now);
      commit([...toastsRef.current, next.toast]);
      armDismissTimer(next.toast);
    } else if (urgent && !toastsRef.current.some((toast) => toast.leaving)) {
      // Screen full: retire the oldest routine toast. Its exit frees the slot
      // and pumps again, so the limit is never exceeded.
      const routine = toastsRef.current.find((toast) => toast.tone !== "error");
      if (routine) dismissToast(routine.id);
    }
    syncPending(pending);

    if (pending.length === 0) return;
    // Wake for the next delayed toast even when the screen is full: a delayed
    // merge needs no slot, and its confirmation may be gone by the time one frees.
    // Otherwise a full screen frees up when dismissToast removes a toast, which
    // pumps again.
    const wakes = pending.filter((item) => item.readyAt > now).map((item) => item.readyAt);
    if (toastsRef.current.length < MAX_VISIBLE && pending.some((item) => item.readyAt <= now)) {
      wakes.push(lastShownAtRef.current + STAGGER_MS);
    }
    if (wakes.length === 0) return;
    pumpTimerRef.current = window.setTimeout(() => pumpRef.current(), Math.max(0, Math.min(...wakes) - now));
  }, [armDismissTimer, commit, dismissToast, mergeIntoRecent, syncPending]);

  useEffect(() => {
    pumpRef.current = pump;
  }, [pump]);

  const showToast = useCallback(
    (message: string, options: ToastOptions = {}) => {
      idRef.current += 1;
      const id = idRef.current;
      const now = Date.now();
      const toast: Toast = { id, message, ...options };
      syncPending([...pendingRef.current, { toast, readyAt: now + (options.delayMs ?? 0), queuedAt: now }]);
      pump();
      return id;
    },
    [pump, syncPending],
  );

  useEffect(() => {
    const timers = timersRef.current;
    const exitTimers = exitTimersRef.current;
    return () => {
      timers.forEach((timerId) => window.clearTimeout(timerId));
      timers.clear();
      exitTimers.forEach((timerId) => window.clearTimeout(timerId));
      exitTimers.clear();
      if (pumpTimerRef.current !== null) window.clearTimeout(pumpTimerRef.current);
    };
  }, []);

  const value = useMemo(() => ({ showToast, dismissToast }), [showToast, dismissToast]);
  const idle = toasts.length === 0 && pendingCount === 0;

  return (
    <ToastContext.Provider value={value}>
      <ToastIdleContext.Provider value={idle}>
        {children}
        <div className="toast-region" role="region" aria-live="polite" aria-label="Notifications">
          {toasts.map((toast) => (
            <div
              key={toast.id}
              className={`toast toast-${toast.tone ?? "info"}${toast.leaving ? " is-leaving" : ""}`}
              role="status"
            >
              <span className="toast-dot" aria-hidden="true" />
              <span className="toast-message">
                {toast.suffix ? toast.message.replace(/\.$/, "") : toast.message}
                {toast.suffix ? (
                  <span className="toast-suffix">
                    <span aria-hidden="true"> · </span>
                    {toast.suffix}
                  </span>
                ) : null}
              </span>
              {toast.action ? (
                <button
                  type="button"
                  className="toast-action"
                  onClick={() => {
                    toast.action?.onClick();
                    dismissToast(toast.id);
                  }}
                >
                  {toast.action.label}
                </button>
              ) : null}
              <button
                type="button"
                className="toast-dismiss"
                aria-label="Dismiss notification"
                onClick={() => dismissToast(toast.id)}
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                  <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      </ToastIdleContext.Provider>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) {
    return {
      showToast: () => 0,
      dismissToast: () => {},
    };
  }
  return context;
}

/** True when no toast is on screen or waiting to appear. */
export function useToastIdle(): boolean {
  return useContext(ToastIdleContext);
}
