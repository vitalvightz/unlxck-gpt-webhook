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
