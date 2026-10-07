import test from "node:test";
import assert from "node:assert/strict";
import "../test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { useTodayCommand, type TodayCommand } from "./use-today-command";

test("an older Today response cannot overwrite a refresh after an injury update", async () => {
  const originalFetch = globalThis.fetch;
  const pending: Array<(response: Response) => void> = [];
  globalThis.fetch = (() => new Promise<Response>(resolve => pending.push(resolve))) as typeof fetch;
  const container = document.createElement("div");
  const root = createRoot(container);
  let current: TodayCommand;
  function Probe() {
    current = useTodayCommand("test-token");
    return <p>{current.state?.today.recommendation_reason}</p>;
  }
  const response = (reason: string) => new Response(JSON.stringify({active_plan: {},
    today: {training_day: "2026-10-07", recommendation_reason: reason}, risk_watch: [], open_injuries: []}),
    { status: 200, headers: { "content-type": "application/json" } });
  try {
    await act(async () => { root.render(<Probe />); });
    assert.equal(pending.length, 1);
    let refreshed: Promise<void>;
    await act(async () => { refreshed = current!.refresh(); });
    assert.equal(pending.length, 2);
    await act(async () => { pending[1](response("New injury restriction")); await refreshed!; });
    assert.equal(container.textContent, "New injury restriction");
    await act(async () => { pending[0](response("Old green guidance")); await new Promise(resolve => setTimeout(resolve, 0)); });
    assert.equal(container.textContent, "New injury restriction");
  } finally {
    await act(async () => { root.unmount(); });
    globalThis.fetch = originalFetch;
  }
});

test("Today publishes before a slow plan read and overlapping refreshes share the pending presentation read", async () => {
  const originalFetch = globalThis.fetch;
  const reads: Array<{ url: string; resolve: (response: Response) => void }> = [];
  globalThis.fetch = ((url: string) => new Promise<Response>(resolve => reads.push({ url: String(url), resolve }))) as typeof fetch;
  const root = createRoot(document.createElement("div"));
  let current: TodayCommand;
  function Probe() { current = useTodayCommand("slow-plan-token"); return null; }
  const json = (value: unknown) => new Response(JSON.stringify(value), {status: 200});
  const today = (reason: string) => json({ active_plan: { id: "plan-1" }, today: {
    training_day: "2026-10-07", recommendation_reason: reason,
  }, open_injuries: [], risk_watch: [] });
  try {
    await act(async () => { root.render(<Probe />); });
    await act(async () => { reads[0].resolve(today("Initial")); });
    assert.equal(current!.isLoading, false);
    assert.equal(current!.state?.today.recommendation_reason, "Initial");
    assert.equal(reads.length, 2); // The initial plan read is still pending.
    let refresh: Promise<void>;
    await act(async () => { refresh = current!.refresh(); });
    const newToday = reads.findLast(read => read.url.endsWith("/api/today"))!;
    await act(async () => { newToday.resolve(today("Fresh restriction")); await refresh!; });
    assert.equal(current!.state?.today.recommendation_reason, "Fresh restriction");
    const plans = reads.filter(read => read.url.includes("/plans/"));
    assert.equal(plans.length, 1);
    await act(async () => { plans[0].resolve(json({ outputs: {}, created_at: "shared" })); });
    assert.equal(current!.planSchedule.createdAt, "shared");
  } finally {
    await act(async () => { root.unmount(); });
    globalThis.fetch = originalFetch;
  }
});

test("ordinary saves reuse presentation; injury, day, plan and TTL changes refresh it; failed reads retry", async () => {
  const originalFetch = globalThis.fetch;
  const originalNow = Date.now;
  let now = 1_000;
  Date.now = () => now;
  let planId = "plan-1", day = "2026-10-07", injury = "", planReads = 0, todayReads = 0;
  let failPlan = false;
  globalThis.fetch = (async (url: string) => {
    if (String(url).endsWith("/api/today")) {
      todayReads++;
      return new Response(JSON.stringify({ active_plan: { id: planId }, today: { training_day: day },
        open_injuries: injury ? [{ id: "injury-1", status: "open", body_area: injury, updated_at: injury }] : [], risk_watch: [] }));
    }
    planReads++;
    return new Response(JSON.stringify(failPlan ? { detail: "Plan read failed" } : { outputs: {}, created_at: `read-${planReads}` }),
      { status: failPlan ? 404 : 200 });
  }) as typeof fetch;
  const root = createRoot(document.createElement("div"));
  let current: TodayCommand;
  function Probe() { current = useTodayCommand("presentation-cache-token"); return null; }
  const refresh = () => act(async () => { await current!.refresh(); });
  try {
    await act(async () => { root.render(<Probe />); });
    await refresh(); await refresh();
    assert.equal(todayReads, 3);
    assert.equal(planReads, 1);
    injury = "chest"; await refresh();
    assert.equal(planReads, 2);
    day = "2026-10-08"; await refresh();
    assert.equal(planReads, 3);
    planId = "plan-2"; await refresh();
    assert.equal(planReads, 4);
    now += 60_001; failPlan = true; await refresh();
    assert.equal(planReads, 5);
    assert.equal(current!.planSchedule.createdAt, "read-4");
    failPlan = false; await refresh();
    assert.equal(planReads, 6);
    assert.equal(current!.planSchedule.createdAt, "read-6");
  } finally {
    await act(async () => { root.unmount(); });
    globalThis.fetch = originalFetch;
    Date.now = originalNow;
  }
});

test("a pending presentation for an old plan cannot replace the newly active plan", async () => {
  const originalFetch = globalThis.fetch;
  const plans: Array<(response: Response) => void> = [];
  let planId = "old-plan";
  globalThis.fetch = ((url: string) => String(url).endsWith("/api/today")
    ? Promise.resolve(new Response(JSON.stringify({ active_plan: { id: planId }, today: { training_day: "2026-10-07" }, open_injuries: [], risk_watch: [] })))
    : new Promise<Response>(resolve => plans.push(resolve))) as typeof fetch;
  const root = createRoot(document.createElement("div"));
  let current: TodayCommand;
  function Probe() { current = useTodayCommand("plan-switch-cache-token"); return null; }
  try {
    await act(async () => { root.render(<Probe />); });
    planId = "new-plan";
    await act(async () => { await current!.refresh(); });
    assert.equal(plans.length, 2);
    await act(async () => { plans[1](new Response(JSON.stringify({ outputs: {}, created_at: "new" }))); });
    await act(async () => { plans[0](new Response(JSON.stringify({ outputs: {}, created_at: "old" }))); });
    assert.equal(current!.planSchedule.createdAt, "new");
  } finally {
    await act(async () => { root.unmount(); });
    globalThis.fetch = originalFetch;
  }
});
