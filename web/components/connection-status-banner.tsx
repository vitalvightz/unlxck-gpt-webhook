"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { useAppSession } from "@/components/auth-provider";
import {
  RECONNECTED_EVENT,
  getConnectivitySnapshot,
  getServerConnectivitySnapshot,
  subscribeConnectivity,
} from "@/lib/connectivity";

const BACK_ONLINE_DWELL_MS = 2500;

export function useConnectivity() {
  return useSyncExternalStore(
    subscribeConnectivity,
    getConnectivitySnapshot,
    getServerConnectivitySnapshot,
  );
}

/**
 * Runs `callback` when the app reconnects (browser back online, or the first
 * successful request after a failure). Screens pass `enabled` only while they
 * are sitting on a load error, so a healthy screen never refetches.
 */
export function useOnReconnect(callback: () => void, enabled: boolean) {
  const callbackRef = useRef(callback);
  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);
  useEffect(() => {
    if (!enabled) return;
    const handler = () => callbackRef.current();
    // RECONNECTED_EVENT also fires for the browser's own "online" event
    // (lib/connectivity re-dispatches it), so one listener covers both.
    window.addEventListener(RECONNECTED_EVENT, handler);
    return () => window.removeEventListener(RECONNECTED_EVENT, handler);
  }, [enabled]);
}

/**
 * App-wide connection pill. Mounted once in the root layout so every surface —
 * guarded or public — gets the same honest signal, and so reconnecting
 * re-hydrates the athlete profile without the user having to find a button.
 */
export function ConnectionStatusBanner() {
  const { offline, degraded } = useConnectivity();
  const { session, hasTransientMeError, refreshMe } = useAppSession();
  const [isRetrying, setIsRetrying] = useState(false);
  const [showBackOnline, setShowBackOnline] = useState(false);
  const refreshRef = useRef(refreshMe);
  const needsProfileRef = useRef(false);

  useEffect(() => {
    refreshRef.current = refreshMe;
    needsProfileRef.current = Boolean(session && hasTransientMeError);
  }, [hasTransientMeError, refreshMe, session]);

  useEffect(() => {
    let dwellTimer: ReturnType<typeof setTimeout> | null = null;
    const onReconnected = () => {
      setShowBackOnline(true);
      if (dwellTimer) clearTimeout(dwellTimer);
      dwellTimer = setTimeout(() => setShowBackOnline(false), BACK_ONLINE_DWELL_MS);
      if (needsProfileRef.current) {
        void refreshRef.current();
      }
    };
    window.addEventListener(RECONNECTED_EVENT, onReconnected);
    return () => {
      if (dwellTimer) clearTimeout(dwellTimer);
      window.removeEventListener(RECONNECTED_EVENT, onReconnected);
    };
  }, []);

  async function handleRetry() {
    if (isRetrying) return;
    setIsRetrying(true);
    try {
      await refreshMe();
    } finally {
      setIsRetrying(false);
    }
  }

  const unreachable = degraded || Boolean(session && hasTransientMeError);

  if (offline) {
    return (
      <div className="connection-lost-banner" role="status" aria-live="polite">
        <span className="connection-lost-dot" aria-hidden="true" />
        <span className="connection-lost-text">Offline · showing what’s already loaded</span>
      </div>
    );
  }

  if (unreachable) {
    return (
      <div className="connection-lost-banner" role="status" aria-live="polite">
        <span className="connection-lost-dot" aria-hidden="true" />
        <span className="connection-lost-text">
          {isRetrying ? "Reconnecting…" : "Can’t reach UNLXCK"}
        </span>
        {session ? (
          <button
            type="button"
            className="connection-lost-retry"
            onClick={() => void handleRetry()}
            disabled={isRetrying}
          >
            {isRetrying ? "Retrying…" : "Retry"}
          </button>
        ) : null}
      </div>
    );
  }

  if (showBackOnline) {
    return (
      <div className="connection-lost-banner connection-restored" role="status" aria-live="polite">
        <span className="connection-lost-dot" aria-hidden="true" />
        <span className="connection-lost-text">Back online</span>
      </div>
    );
  }

  return null;
}
