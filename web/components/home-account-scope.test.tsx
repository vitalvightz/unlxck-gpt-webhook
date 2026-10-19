import assert from "node:assert/strict";
import test from "node:test";
import "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { NextIntlClientProvider } from "next-intl";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";
import { PathnameContext, SearchParamsContext } from "next/dist/shared/lib/hooks-client-context.shared-runtime";
import { AppSessionContext } from "./auth-provider";
import { XpContext } from "./xp-provider";
import HomePage from "../app/page";
import messages from "../messages/en.json";
import { createFreshXpProgress } from "@/lib/xp-progress";
import type { MeResponse } from "@/lib/types";

const TODAY = "2026-10-19";
const me = (id: string) => ({
  profile: { athlete_id: id, role: "athlete", starting_path: "tracking_first", health_consent_granted: true,
    technical_style: ["boxing"], training_habits: { enabled: true, decisions: [] } },
  plan_count: 0, latest_plan: null, latest_intake: null,
}) as unknown as MeResponse;

test("Home never shows the previous account's training after an account switch", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const token = new Headers(init?.headers).get("authorization");
    const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
    if (url.includes("/api/today")) {
      return json({ active_plan: {}, today: { training_day: TODAY, recommendation_state: "train_as_planned", decision_tier: "green",
        next_session: {}, session_scope: "none", session_label: "", completion_status: "not_started" },
      risk_watch: [], open_injuries: [], week_summary: {}, quick_actions: [] });
    }
    if (url.includes("/api/training/history")) {
      // Athlete B's history is still loading when the switch happens.
      if (token === "Bearer token-b") return new Promise<Response>(() => {});
      return json({ sessions: [{ id: "a-1", source: "external", training_day: TODAY, status: "done", title: "Boxing · Pads",
        activity: "boxing", sport: "boxing", session_type: "pads", duration_minutes: 60, effort: "hard", plan_id: null }],
      next_before_day: null });
    }
    return json({});
  }) as typeof fetch;
  const router = { push() {}, replace() {}, refresh() {}, back() {}, forward() {}, prefetch() {}, bfcacheId: "home" };
  const xp = { progress: createFreshXpProgress(), isHydrated: true, isRefreshing: false, error: null, feedback: null,
    refresh: async () => {}, dismissFeedback() {} };
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const render = (token: string, athlete: MeResponse) => root.render(
    <NextIntlClientProvider locale="en" timeZone="Europe/London" messages={messages}>
      <AppRouterContext.Provider value={router}>
        <PathnameContext.Provider value="/"><SearchParamsContext.Provider value={new URLSearchParams()}>
          <AppSessionContext.Provider value={{ isReady: true, isMeHydrated: true, hasTransientMeError: false,
            session: { access_token: token } as never, me: athlete, previewAppearanceMode() {}, refreshMe: async () => {},
            replaceMe() {}, signOut: async () => {} }}>
            <XpContext.Provider value={xp}><HomePage /></XpContext.Provider>
          </AppSessionContext.Provider>
        </SearchParamsContext.Provider></PathnameContext.Provider>
      </AppRouterContext.Provider>
    </NextIntlClientProvider>,
  );
  const strip = () => host.querySelector('[aria-label="Training status"]')?.textContent ?? "";
  try {
    await act(async () => render("token-a", me("athlete-a")));
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)); });
    assert.match(strip(), /Last 7 days1 session/);
    assert.match(host.textContent ?? "", /Logged today/);

    await act(async () => render("token-b", me("athlete-b")));
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)); });
    // B's read has not returned: nothing from A, and no claims about B either.
    assert.doesNotMatch(strip(), /1 session/);
    assert.match(strip(), /Last 7 days—/);
    assert.doesNotMatch(host.textContent ?? "", /Logged today|Boxing · Pads/);
  } finally {
    act(() => root.unmount());
    host.remove();
    globalThis.fetch = originalFetch;
  }
});
