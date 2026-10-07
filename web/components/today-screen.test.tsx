import test from "node:test";
import assert from "node:assert/strict";
import "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { AppSessionContext } from "./auth-provider";
import { ToastProvider } from "./toast-provider";
import { TodayScreen } from "./today-screen";
import type { TodayCommandView } from "@/lib/types";

test("a failed post-save refresh keeps the check-in form mounted and offers retry", async () => {
  const originalFetch = globalThis.fetch;
  let todayReads = 0;
  const state: TodayCommandView = { active_plan: {id: "plan-1", name: "Camp", phase: "SPP"},
    today: {training_day: "2026-10-07", recommendation_state: "not_checked_in",
      decision_tier: "not_checked_in", warnings: [], next_session: {}, completion_status: "not_started",
      session_scope: "none", session_label: "No session"},
    open_injuries: [], risk_watch: [], week_summary: {}, quick_actions: [] };
  const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {status});
  globalThis.fetch = (async (input: string) => {
    if (String(input).endsWith("/api/today")) {
      return ++todayReads === 1 ? json(state) : json({detail: "Temporarily unavailable"}, 400);
    }
    if (String(input).endsWith("/api/today/checkin")) {
      return json({recommendation_state: "train_as_planned"});
    }
    if (String(input).includes("/api/plans/")) return json({outputs: {}});
    return json({logs: [], pending: [], rehab_response_prompts: []});
  }) as typeof fetch;
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  try {
    await act(async () => { root.render(<AppSessionContext.Provider value={{isReady: true,
      isMeHydrated: true, hasTransientMeError: false, session: {access_token: "test-token"}, me: null,
      previewAppearanceMode: () => {}, refreshMe: async () => {}, replaceMe: () => {}, signOut: async () => {}}}>
      <ToastProvider><TodayScreen /></ToastProvider>
    </AppSessionContext.Provider>); });
    const form = container.querySelector("form")!;
    assert.ok(form);
    const submit = form.querySelector<HTMLButtonElement>('[type="submit"]')!;
    await act(async () => { submit.click(); });
    assert.equal(todayReads, 2);
    assert.equal(container.querySelector("form"), form);
    assert.match(container.textContent ?? "", /Today could not refresh/);
    assert.match(container.textContent ?? "", /Retry Today/);
    assert.equal(submit.disabled, false);
  } finally {
    await act(async () => { root.unmount(); });
    container.remove();
    globalThis.fetch = originalFetch;
  }
});
