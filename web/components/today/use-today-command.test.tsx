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

test("Today publishes and refresh resolves before a slow plan read; older plan reads cannot overwrite it", async () => {
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
    assert.equal(plans.length, 2);
    await act(async () => { plans[1].resolve(json({ outputs: {}, created_at: "new" })); });
    assert.equal(current!.planSchedule.createdAt, "new");
    await act(async () => { plans[0].resolve(json({ outputs: {}, created_at: "old" })); });
    assert.equal(current!.planSchedule.createdAt, "new");
  } finally {
    await act(async () => { root.unmount(); });
    globalThis.fetch = originalFetch;
  }
});
