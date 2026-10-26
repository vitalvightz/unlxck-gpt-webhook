import test from "node:test";
import assert from "node:assert/strict";
import "../test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { applyExerciseChange, getPlan, submitTodayInjuryCheckin } from "@/lib/api";
import type { TodayInjuryCheckinRequest } from "@/lib/types";
import { XP_REFRESH_EVENT } from "@/lib/xp-events";
import { useTodayCommand, type TodayCommand } from "./use-today-command";

test("an older Today response cannot overwrite a refresh after an injury update", async () => {
  const originalFetch = globalThis.fetch;
  const pending: Array<(response: Response) => void> = [];
  globalThis.fetch = ((_url: string, init?: RequestInit) => init?.method === "POST"
    ? Promise.resolve(new Response(JSON.stringify({}), { status: 200 }))
    : new Promise<Response>(resolve => pending.push(resolve))) as typeof fetch;
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
    // The update is a write, so the refresh cannot join the earlier read.
    await submitTodayInjuryCheckin("test-token", {} as TodayInjuryCheckinRequest);
    let refreshed: Promise<void>;
    await act(async () => { refreshed = current!.refresh(); });
    assert.equal(pending.length, 2);
    assert.equal(current!.isRefreshing, true);
    await act(async () => { pending[1](response("New injury restriction")); await refreshed!; });
    assert.equal(container.textContent, "New injury restriction");
    assert.equal(current!.isRefreshing, false);
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

test("a failed post-save refresh keeps entries with an error and a later refresh retries", async () => {
  const originalFetch = globalThis.fetch;
  let fail = false;
  let reason = "Before training";
  globalThis.fetch = (async () => fail
    ? new Response(JSON.stringify({ detail: "Readiness unavailable" }), { status: 400 })
    : new Response(JSON.stringify({ active_plan: {}, today: { training_day: "2026-10-18", recommendation_reason: reason },
      open_injuries: [], risk_watch: [] }))) as typeof fetch;
  const root = createRoot(document.createElement("div"));
  let current: TodayCommand;
  function Probe() { current = useTodayCommand("refresh-failure-token"); return null; }
  try {
    await act(async () => { root.render(<Probe />); });
    fail = true;
    await act(async () => { await current!.refresh(); });
    assert.equal(current!.isRefreshing, false);
    assert.match(current!.error!, /Readiness unavailable/);
    assert.equal(current!.state?.today.recommendation_reason, "Before training");
    fail = false;
    reason = "After training";
    await act(async () => { await current!.refresh(); });
    assert.equal(current!.error, null);
    assert.equal(current!.state?.today.recommendation_reason, "After training");
  } finally {
    await act(async () => { root.unmount(); });
    globalThis.fetch = originalFetch;
  }
});

test("opening Today reuses the plan Home just read and leaves XP alone; refreshes and changes read fresh", async () => {
  const originalFetch = globalThis.fetch;
  const reads: string[] = [];
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    const path = new URL(String(url), "http://127.0.0.1").pathname;
    if (init?.method && init.method !== "GET") return new Response(JSON.stringify({}));
    reads.push(path);
    return new Response(JSON.stringify(path === "/api/today"
      ? { active_plan: { id: "plan-1" }, today: { training_day: "2026-10-07" }, open_injuries: [], risk_watch: [] }
      : { outputs: {}, created_at: `read-${reads.length}` }));
  }) as typeof fetch;
  let xpRefreshes = 0;
  const onXp = () => { xpRefreshes += 1; };
  window.addEventListener(XP_REFRESH_EVENT, onXp);
  const root = createRoot(document.createElement("div"));
  let current: TodayCommand;
  function Probe() { current = useTodayCommand("navigation-token"); return null; }
  const settle = () => act(async () => { await new Promise(resolve => setTimeout(resolve, 0)); });
  try {
    await getPlan("navigation-token", "plan-1"); // Home's countdown read.
    await act(async () => { root.render(<Probe />); });
    await settle();
    assert.deepEqual(reads, ["/api/plans/plan-1", "/api/today"]);
    assert.equal(current!.planSchedule.createdAt, "read-1");
    assert.equal(xpRefreshes, 0);
    // A refresh the screen asks for (after a save) still refreshes XP.
    await act(async () => { await current!.refresh(); });
    assert.equal(xpRefreshes, 1);
    // An exercise change is a write; the plan is read again past every cache.
    await applyExerciseChange("navigation-token", "plan-1", {} as never);
    await act(async () => { current!.patchSession("2026-10-07", null); });
    await settle();
    assert.equal(reads.filter(path => path === "/api/plans/plan-1").length, 2);
    assert.equal(current!.planSchedule.createdAt, `read-${reads.lastIndexOf("/api/plans/plan-1") + 1}`);
  } finally {
    window.removeEventListener(XP_REFRESH_EVENT, onXp);
    await act(async () => { root.unmount(); });
    globalThis.fetch = originalFetch;
  }
});
