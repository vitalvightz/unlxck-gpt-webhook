// Browser online events are hints. Only a fresh, validated response from the
// UNLXCK health endpoint can confirm recovery; ordinary requests cannot.
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
let failureRevision = 0;
let recoveryRequest: Promise<boolean> | null = null;
let recoveryController: AbortController | null = null;
let recoveryTimer: ReturnType<typeof setTimeout> | null = null;
let recoveryDelayMs = 3000;

function scheduleRecovery() {
  if (recoveryTimer || recoveryRequest || !listeners.size || snapshot.offline || !snapshot.degraded) return;
  recoveryTimer = setTimeout(() => {
    recoveryTimer = null;
    void checkApiConnection();
  }, recoveryDelayMs);
}

function clearRecoveryTimer() {
  if (recoveryTimer) clearTimeout(recoveryTimer);
  recoveryTimer = null;
}

/** Deduplicated, uncached API check, including body download in the timeout. */
export function checkApiConnection(): Promise<boolean> {
  attachWindowListeners();
  if (isBrowserOffline()) {
    reportNetworkFailure();
    return Promise.resolve(false);
  }
  if (recoveryRequest) return recoveryRequest;
  clearRecoveryTimer();
  const revision = failureRevision;
  const controller = new AbortController();
  recoveryController = controller;
  const timeout = setTimeout(() => controller.abort(), 8000);
  recoveryRequest = (async () => {
    try {
      const response = await fetch("/api/health", {
        cache: "no-store",
        credentials: "same-origin",
        redirect: "error",
        signal: controller.signal,
      });
      if (!response.ok || !response.headers.get("content-type")?.includes("application/json")) return false;
      const body: unknown = await response.json();
      if (!body || typeof body !== "object" || !("ok" in body) || body.ok !== true ||
          !("app" in body) || body.app !== "unlxck-fight-camp-api") return false;
      // A newer failure or offline event invalidates even a successful probe.
      if (controller.signal.aborted || revision !== failureRevision || isBrowserOffline()) return false;
      recoveryDelayMs = 3000;
      setSnapshot(ONLINE_SNAPSHOT);
      return true;
    } catch {
      return false;
    } finally {
      clearTimeout(timeout);
    }
  })().then((healthy) => {
    recoveryRequest = null;
    recoveryController = null;
    if (!healthy) {
      recoveryDelayMs = Math.min(recoveryDelayMs * 2, 30000);
      reportNetworkFailure();
    }
    return healthy;
  });
  return recoveryRequest;
}

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
  window.addEventListener("offline", onOffline);
  window.addEventListener("online", onOnline);
}

function onOffline() {
  failureRevision += 1;
  clearRecoveryTimer();
  recoveryController?.abort();
  setSnapshot({ offline: true, degraded: false });
}

function onOnline() {
  setSnapshot({ offline: false, degraded: true });
  void checkApiConnection();
}

export function subscribeConnectivity(listener: () => void): () => void {
  attachWindowListeners();
  listeners.add(listener);
  scheduleRecovery();
  return () => {
    listeners.delete(listener);
    if (!listeners.size) clearRecoveryTimer();
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
  failureRevision += 1;
  setSnapshot({ offline: isBrowserOffline(), degraded: !isBrowserOffline() });
  scheduleRecovery();
}

// Avoid automatic reload loops if the API recovers but a chunk is still missing.
export function reloadAfterRecovery(manual = false): boolean {
  try {
    const previous = Number(window.history.state?.unlxckRecoveryReloadAt);
    if (!manual && previous && Date.now() - previous < 60000) return false;
    window.history.replaceState({ ...window.history.state, unlxckRecoveryReloadAt: Date.now() }, "");
  } catch {
    // Without a guard that survives reload, leave recovery to an explicit retry.
    if (!manual) return false;
  }
  window.location.reload();
  return true;
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
  clearRecoveryTimer();
  recoveryController?.abort();
  if (typeof window !== "undefined") {
    window.removeEventListener("online", onOnline);
    window.removeEventListener("offline", onOffline);
  }
  snapshot = ONLINE_SNAPSHOT;
  listeners.clear();
  windowListenersAttached = false;
  failureRevision = 0;
  recoveryDelayMs = 3000;
}
