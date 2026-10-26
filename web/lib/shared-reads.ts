/**
 * Request sharing for a few read-only API calls.
 *
 * - Identical reads in flight together share one network request.
 * - A caller may opt in to a result resolved at most `reuseForMs` ago.
 *
 * Both are keyed by the bearer token and the full request path, so separate
 * sessions or accounts never share a request or a result. Both also end at
 * the first write: every non-neutral API write starts a new epoch, drops held
 * results, and stops later callers joining reads that started before it. While
 * a write is in flight nothing is shared at all. Results live in memory only,
 * for at most SHARED_READ_MAX_AGE_MS, and never more than MAX_HELD of them.
 * See docs/performance/frontend-optimisation-results.md.
 */

export const SHARED_READ_MAX_AGE_MS = 30_000;
const MAX_HELD = 12;

type InFlight = {
  promise: Promise<unknown>;
  controller: AbortController;
  consumers: number;
  settled: boolean;
};

const inFlight = new Map<string, InFlight>();
const held = new Map<string, { value: unknown; at: number }>();
let writeEpoch = 0;
let writesInFlight = 0;

// Monotonic: a wall-clock change can neither extend nor revive a held result.
const now = () => performance.now();

function abortReason(signal: AbortSignal): unknown {
  return signal.reason ?? new DOMException("The operation was aborted.", "AbortError");
}

function pruneHeld() {
  const oldest = now() - SHARED_READ_MAX_AGE_MS;
  for (const [key, entry] of held) if (entry.at < oldest) held.delete(key);
}

function hold(key: string, value: unknown) {
  held.delete(key);
  held.set(key, { value, at: now() });
  while (held.size > MAX_HELD) held.delete(held.keys().next().value!);
}

function consume<T>(key: string, entry: InFlight, signal?: AbortSignal): Promise<T> {
  entry.consumers += 1;
  return new Promise<T>((resolve, reject) => {
    let done = false;
    const finish = () => {
      done = true;
      entry.consumers -= 1;
      signal?.removeEventListener("abort", onAbort);
    };
    // One consumer leaving never cancels another's read; the last one to leave
    // cancels the network request nobody is waiting for any more.
    const onAbort = () => {
      if (done) return;
      finish();
      if (entry.consumers === 0 && !entry.settled) {
        if (inFlight.get(key) === entry) inFlight.delete(key);
        entry.controller.abort();
      }
      reject(abortReason(signal!));
    };
    signal?.addEventListener("abort", onAbort, { once: true });
    entry.promise.then(
      (value) => { if (!done) { finish(); resolve(value as T); } },
      (error) => { if (!done) { finish(); reject(error); } },
    );
  });
}

export type SharedReadOptions = {
  /** Cancels this caller's wait; the read continues while others need it. */
  signal?: AbortSignal;
  /** Keep the resolved result so callers passing `reuseForMs` can use it. */
  hold?: boolean;
  /** Accept a result resolved this recently (capped at SHARED_READ_MAX_AGE_MS). */
  reuseForMs?: number;
};

export function sharedRead<T>(
  token: string,
  path: string,
  load: (signal: AbortSignal) => Promise<T>,
  { signal, hold: holdResult = false, reuseForMs = 0 }: SharedReadOptions = {},
): Promise<T> {
  // An already-cancelled caller gets nothing and starts nothing.
  if (signal?.aborted) return Promise.reject(abortReason(signal));
  const key = `${token}\u0000${path}`;
  const sharing = writesInFlight === 0;
  if (sharing && reuseForMs > 0) {
    pruneHeld();
    const result = held.get(key);
    if (result && now() - result.at <= Math.min(reuseForMs, SHARED_READ_MAX_AGE_MS)) {
      return Promise.resolve(result.value as T);
    }
  }
  let entry = sharing ? inFlight.get(key) : undefined;
  if (!entry) {
    const epoch = writeEpoch;
    const controller = new AbortController();
    const created: InFlight = { controller, consumers: 0, settled: false, promise: Promise.resolve() };
    created.promise = load(controller.signal)
      .then((value) => {
        // Only a read that began and ended with no write in between is reusable.
        if (holdResult && epoch === writeEpoch && writesInFlight === 0) hold(key, value);
        return value;
      })
      .finally(() => {
        created.settled = true;
        if (inFlight.get(key) === created) inFlight.delete(key);
      });
    if (sharing) inFlight.set(key, created);
    entry = created;
  }
  return consume<T>(key, entry, signal);
}

function invalidate() {
  writeEpoch += 1;
  held.clear();
  inFlight.clear();
}

/** Marks an API write. Call the returned function once it has settled. */
export function beginSharedReadWrite(): () => void {
  writesInFlight += 1;
  invalidate();
  let ended = false;
  return () => {
    if (ended) return;
    ended = true;
    writesInFlight -= 1;
    invalidate();
  };
}

/** Forget everything, e.g. at sign-out. In-flight callers still settle. */
export function clearSharedReads() {
  invalidate();
}
