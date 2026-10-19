"use client";

import { useEffect, useRef, useState } from "react";
import {
  RECONNECTED_EVENT,
  checkApiConnection,
  reloadAfterRecovery,
  reportNetworkFailure,
  subscribeConnectivity,
} from "@/lib/connectivity";

/** Boundaries may replace the root layout, so recovery must work without providers. */
export function useConnectionRecovery(enabled: boolean) {
  const manualRetry = useRef(false);
  const [retrying, setRetrying] = useState(false);
  const [retryFailed, setRetryFailed] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    let attempted = false;
    const onRecovered = () => {
      if (attempted || manualRetry.current) return;
      attempted = true;
      reloadAfterRecovery();
    };
    window.addEventListener(RECONNECTED_EVENT, onRecovered);
    const unsubscribe = subscribeConnectivity(() => {});
    reportNetworkFailure();
    void checkApiConnection();
    return () => {
      unsubscribe();
      window.removeEventListener(RECONNECTED_EVENT, onRecovered);
    };
  }, [enabled]);

  async function retryConnection() {
    if (manualRetry.current) return;
    manualRetry.current = true;
    setRetrying(true);
    setRetryFailed(false);
    try {
      if (await checkApiConnection()) reloadAfterRecovery(true);
      else setRetryFailed(true);
    } finally {
      manualRetry.current = false;
      setRetrying(false);
    }
  }

  return { retrying, retryFailed, retryConnection };
}
