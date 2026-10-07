import assert from "node:assert/strict";
import test from "node:test";
import "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { AppSessionContext } from "./auth-provider";
import { HistoryScreen } from "./history-screen";

test("failed History tabs can be retried without losing the Sessions cache", async () => {
  process.env.NEXT_PUBLIC_API_DEBUG = "false";
  const originalFetch = globalThis.fetch;
  const requests: string[] = [];
  let fail = true;
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    requests.push(url);
    assert.equal(new Headers(init?.headers).get("authorization"), "Bearer token");
    const isSessions = url.includes("session-completions");
    const failed = !isSessions && fail;
    const body = failed ? { detail: "invalid authentication token" }
      : url.includes("sparring-logs") ? { logs: [] } : url.includes("history/exercises") ? { logs: [], next_offset: null } : [];
    return new Response(JSON.stringify(body), {
      status: failed ? 401 : 200,
      headers: { "content-type": "application/json" },
    });
  };
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const click = async (label: string) => {
    const button = Array.from(container.querySelectorAll("button")).find((item) => item.textContent === label);
    assert.ok(button, `Missing ${label} button`);
    await act(async () => button.click());
  };
  try {
    await act(async () => root.render(
      <AppSessionContext.Provider value={{
        session: { access_token: "token" }, me: null, isReady: true, isMeHydrated: true,
        hasTransientMeError: false, refreshMe: async () => {}, signOut: async () => {},
        replaceMe: () => {}, previewAppearanceMode: () => {},
      }}>
        <HistoryScreen />
      </AppSessionContext.Provider>,
    ));
    assert.match(container.textContent ?? "", /No sessions logged yet/);
    const initialSessionRequests = requests.filter((url) => url.includes("session-completions")).length;
    for (const tab of ["Exercises", "Sparring", "Check-ins", "Injuries"]) {
      fail = true;
      await click(tab);
      assert.match(container.querySelector('[role="alert"]')?.textContent ?? "", /invalid authentication token/);
      fail = false;
      await click("Retry");
      assert.equal(container.querySelector('[role="alert"]'), null);
      assert.ok(container.querySelector('[role="status"]'));
    }
    await click("Sessions");
    assert.equal(requests.filter((url) => url.includes("session-completions")).length, initialSessionRequests);
    assert.ok(requests.includes("/api/injury-flags?include_resolved=true"));
  } finally {
    act(() => root.unmount());
    container.remove();
    globalThis.fetch = originalFetch;
  }
});


test("switching accounts drops history before the next account finishes loading", async () => {
  const originalFetch = globalThis.fetch;
  let finishSecond: ((response: Response) => void) | undefined;
  globalThis.fetch = async (_input, init) => {
    if (new Headers(init?.headers).get("authorization") === "Bearer first") {
      return new Response(JSON.stringify([{ id: "old", session_title: "First account session", status: "done", training_day: "2026-10-07" }]), { status: 200 });
    }
    return new Promise<Response>((resolve) => { finishSecond = resolve; });
  };
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const render = (token: string) => root.render(<AppSessionContext.Provider value={{
    session: { access_token: token }, me: null, isReady: true, isMeHydrated: true,
    hasTransientMeError: false, refreshMe: async () => {}, signOut: async () => {},
    replaceMe: () => {}, previewAppearanceMode: () => {},
  }}><HistoryScreen /></AppSessionContext.Provider>);
  try {
    await act(async () => render("first"));
    assert.match(container.textContent ?? "", /First account session/);
    await act(async () => render("second"));
    assert.equal(container.textContent?.includes("First account session"), false);
    await act(async () => finishSecond?.(new Response("[]", { status: 200 })));
    assert.match(container.textContent ?? "", /No sessions logged yet/);
  } finally {
    act(() => root.unmount());
    container.remove();
    globalThis.fetch = originalFetch;
  }
});
