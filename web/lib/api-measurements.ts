/** Explicit local capture only. No tokens, URL values, bodies or errors retained. */
export type ApiMeasurement = { endpoint: string; method: string; headersMs: number; bodyCompleteMs: number | null; responseBytes: number | null; failed: boolean; repeated: boolean };
const pendingBodies = new WeakMap<Response, { started: number; row: ApiMeasurement }>();
export function completeApiMeasurement(response: Response) {
  const pending = pendingBodies.get(response);
  if (pending) {
    pending.row.bodyCompleteMs = performance.now() - pending.started;
    pendingBodies.delete(response);
  }
}
let capture: ReturnType<typeof createCapture> | null = null;
function createCapture(workflow: string, trigger: "navigation" | "mutation" | "refresh") {
  const rows: ApiMeasurement[] = [];
  const identities: string[] = [];
  return { workflow, trigger, salt: crypto.randomUUID(), started: performance.now(), rows, identities };
}
export function beginApiMeasurement(workflow: string, trigger: "navigation" | "mutation" | "refresh") {
  if (capture) throw new Error("An API measurement is already active");
  const current = createCapture(workflow, trigger);
  capture = current;
  return () => {
    if (capture === current) capture = null;
    current.identities.length = 0;
    return { workflow, trigger, durationMs: performance.now() - current.started, requests: current.rows };
  };
}
// Strict allowlist: unknown paths never enter output, including free-text IDs.
export function safeEndpoint(path: string) {
  const pathname = path.split("?")[0];
  if (/^\/api\/(me|today|plans|xp\/progress|training\/history)$/.test(pathname)) return pathname;
  if (/^\/api\/plans\/[^/]+$/.test(pathname)) return "/api/plans/:id";
  if (/^\/api\/today\/(checkin|injury-checkin|rehab-responses|session-completion|exercise-log|exercise-logs)$/.test(pathname)) return pathname;
  return "/api/:other";
}
export async function measuredApiFetch(path: string, url: string, init: RequestInit) {
  const current = capture;
  if (!current) return fetch(url, init);
  const method = init.method ?? "GET";
  // Salted exact identity; no URL parameter values retained in capture state.
  // Only safe reads are duplicate candidates; mutation bodies may differ.
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`${current.salt} ${method} ${path}`));
  const identity = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
  const repeated = ["GET", "HEAD"].includes(method) && current.identities.includes(identity);
  current.identities.push(identity);
  const started = performance.now();
  let response: Response | undefined;
  try {
    response = await fetch(url, init);
    return response;
  } finally {
    const length = response?.headers.get("content-length");
    const row: ApiMeasurement = { endpoint: safeEndpoint(path), method,
      headersMs: performance.now() - started, bodyCompleteMs: null,
      responseBytes: length && /^\d+$/.test(length) ? Number(length) : null,
      failed: !response?.ok, repeated };
    current.rows.push(row);
    if (response) pendingBodies.set(response, { started, row });
  }
}
