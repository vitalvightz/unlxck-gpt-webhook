// Single source of truth for "can the app reach the network right now".
//
// Two independent signals feed it:
// - the browser's own online/offline flag (`navigator.onLine` + its events),
//   which is reliable when it says *offline* and is what lets requests fail
//   fast instead of sitting on a 60s timeout;
// - real request outcomes reported by lib/api.ts, which catch the cases the
//   browser flag misses (captive wifi, dead backend route, flaky 4G).
//
// This module must not import lib/api.ts (api.ts imports it).

/** Thrown by the API client when a request could not reach the server at all. */
export const RETRYABLE_NETWORK_MESSAGE = "Connection issue. Try again in a minute.";
/** Thrown instead of attempting a request while the device reports no connection. */
export const OFFLINE_NETWORK_MESSAGE = "You're offline. Reconnect to keep training.";

export const RECONNECTED_EVENT = "unlxck:reconnected";

const NETWORK_ERROR_MESSAGES = new Set([RETRYABLE_NETWORK_MESSAGE, OFFLINE_NETWORK_MESSAGE]);
// Raw fetch / dynamic-import failures as browsers phrase them.
const RAW_NETWORK_ERROR_PATTERN =
  /failed to fetch|load failed|networkerror|network request failed|loading chunk|chunkloaderror|failed to load chunk|importing a module script failed|error loading dynamically imported module/i;

export function isBrowserOffline(): boolean {
  return typeof navigator !== "undefined" && navigator.onLine === false;
}

/** True for any failure that came from the connection rather than the server's answer. */
export function isNetworkFailure(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }
  if (NETWORK_ERROR_MESSAGES.has(error.message)) {
    return true;
  }
  return error.name === "ChunkLoadError" || RAW_NETWORK_ERROR_PATTERN.test(error.message);
}

/**
 * User-facing copy for a failed load: offline-aware when the failure came from
 * the connection, otherwise the caller's own fallback.
 */
export function describeLoadFailure(error: unknown, fallback: string): string {
  if (isBrowserOffline()) {
    return OFFLINE_NETWORK_MESSAGE;
  }
  if (isNetworkFailure(error)) {
    return RETRYABLE_NETWORK_MESSAGE;
  }
  return fallback;
}

// ---------------------------------------------------------------------------
// Connectivity store (useSyncExternalStore-compatible)
// ---------------------------------------------------------------------------

export type ConnectivitySnapshot = {
  /** Device reports no connection. */
  offline: boolean;
  /** Device claims a connection but the last request still could not reach the server. */
  degraded: boolean;
};

const ONLINE_SNAPSHOT: ConnectivitySnapshot = { offline: false, degraded: false };
let snapshot: ConnectivitySnapshot = ONLINE_SNAPSHOT;
const listeners = new Set<() => void>();
let windowListenersAttached = false;

function setSnapshot(next: ConnectivitySnapshot) {
  if (next.offline === snapshot.offline && next.degraded === snapshot.degraded) {
    return;
  }
  const wasDown = snapshot.offline || snapshot.degraded;
  snapshot = next.offline || next.degraded ? next : ONLINE_SNAPSHOT;
  listeners.forEach((listener) => listener());
  if (wasDown && !snapshot.offline && !snapshot.degraded && typeof window !== "undefined") {
    window.dispatchEvent(new Event(RECONNECTED_EVENT));
  }
}

function attachWindowListeners() {
  if (windowListenersAttached || typeof window === "undefined") {
    return;
  }
  windowListenersAttached = true;
  snapshot = isBrowserOffline() ? { offline: true, degraded: false } : snapshot;
  window.addEventListener("offline", () => setSnapshot({ offline: true, degraded: false }));
  // The browser flag flipping back is a hint, not proof: clear "offline" but
  // leave confirmation to the next successful request.
  window.addEventListener("online", () => setSnapshot({ offline: false, degraded: false }));
}

export function subscribeConnectivity(listener: () => void): () => void {
  attachWindowListeners();
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getConnectivitySnapshot(): ConnectivitySnapshot {
  attachWindowListeners();
  return snapshot;
}

export function getServerConnectivitySnapshot(): ConnectivitySnapshot {
  return ONLINE_SNAPSHOT;
}

export function reportNetworkFailure(): void {
  setSnapshot({ offline: isBrowserOffline(), degraded: !isBrowserOffline() });
}

export function reportNetworkSuccess(): void {
  if (snapshot.offline || snapshot.degraded) {
    setSnapshot({ offline: false, degraded: false });
  }
}

/**
 * Backoff that wakes early: resolves after `maxWaitMs`, or as soon as the
 * browser reports it is back online, or when `signal` aborts.
 */
export function waitForOnline(maxWaitMs: number, signal?: AbortSignal | null): Promise<void> {
  return new Promise((resolve) => {
    if (typeof window === "undefined") {
      resolve();
      return;
    }
    let timer: ReturnType<typeof setTimeout> | null = null;
    const done = () => {
      if (timer) clearTimeout(timer);
      window.removeEventListener("online", done);
      signal?.removeEventListener("abort", done);
      resolve();
    };
    timer = setTimeout(done, maxWaitMs);
    window.addEventListener("online", done, { once: true });
    signal?.addEventListener("abort", done, { once: true });
  });
}

/** Test-only: reset module state between cases. */
export function __resetConnectivityForTests(): void {
  snapshot = ONLINE_SNAPSHOT;
  listeners.clear();
  windowListenersAttached = false;
}
