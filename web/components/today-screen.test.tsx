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

async function renderToday(state: TodayCommandView, me: unknown) {
  const originalFetch = globalThis.fetch;
  const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {status});
  globalThis.fetch = (async (input: string) => {
    if (String(input).endsWith("/api/today")) return json(state);
    if (String(input).includes("/api/training/history")) return json({sessions: []});
    return json({logs: [], pending: [], rehab_response_prompts: []});
  }) as typeof fetch;
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => { root.render(<AppSessionContext.Provider value={{isReady: true,
    isMeHydrated: true, hasTransientMeError: false, session: {access_token: "test-token"},
    me: me as never, previewAppearanceMode: () => {}, refreshMe: async () => {}, replaceMe: () => {},
    signOut: async () => {}}}>
    <ToastProvider><TodayScreen /></ToastProvider>
  </AppSessionContext.Provider>); });
  return {container, cleanup: async () => {
    await act(async () => { root.unmount(); });
    container.remove();
    globalThis.fetch = originalFetch;
  }};
}

const NO_PLAN_STATE: TodayCommandView = { active_plan: {},
  today: {training_day: "2026-10-07", recommendation_state: "not_checked_in", decision_tier: "not_checked_in",
    warnings: [], next_session: {}, completion_status: "not_started", session_scope: "none", session_label: "No session"},
  open_injuries: [], risk_watch: [], week_summary: {}, quick_actions: [] };
const CONSENTED = {profile: {role: "athlete", health_consent_granted: true, athlete_timezone: "Europe/London"}, plan_count: 0};

test("without a plan, the same Today shares logging and injuries but never claims readiness", async () => {
  const {container, cleanup} = await renderToday(NO_PLAN_STATE, CONSENTED);
  try {
    assert.equal(container.querySelectorAll("h1").length, 1);
    const status = container.querySelector('[aria-label="Today command status"]')?.textContent ?? "";
    assert.match(status, /Readiness.*Not assessed/);
    assert.doesNotMatch(status, /Check-in|Due|Done/);
    assert.equal(container.querySelector("#today-checkin"), null);
    assert.equal(container.querySelector("#today-session"), null);
    assert.equal(container.querySelector("#today-decision"), null);
    assert.ok(container.querySelector("#today-training-log [aria-label='Log Training']"));
    assert.ok(container.querySelector(".today-injury-add-trigger"));
    assert.match(container.textContent ?? "", /Build S&C plan/);
    assert.doesNotMatch(container.textContent ?? "", /View plan/);
  } finally { await cleanup(); }
});

test("without a plan, a current injury hold still leads Today", async () => {
  const held: TodayCommandView = {...NO_PLAN_STATE,
    today: {...NO_PLAN_STATE.today, recommendation_state: "pull_back", decision_tier: "stop"},
    open_injuries: [{id: "flag-1", athlete_id: "athlete-1", source: "checkin", body_area: "left knee",
      description: "sharp pain", severity: "severe", status: "open", created_at: "2026-10-07T08:00:00Z",
      updated_at: "2026-10-07T08:00:00Z"}]};
  const {container, cleanup} = await renderToday(held, CONSENTED);
  try {
    assert.match(container.querySelector("#today-decision")?.textContent ?? "", /STOP.*Active severe injury: Left knee/);
    assert.match(container.querySelector('[aria-label="Today command status"]')?.textContent ?? "", /1 active/);
    assert.equal(container.querySelector("#today-checkin"), null);
  } finally { await cleanup(); }
});

test("without health-data consent the injury form is not offered", async () => {
  const {container, cleanup} = await renderToday(NO_PLAN_STATE,
    {...CONSENTED, profile: {...CONSENTED.profile, health_consent_granted: false}});
  try {
    assert.equal(container.querySelector(".today-injury-add-trigger"), null);
    assert.match(container.querySelector("#today-injury")?.textContent ?? "", /needs your health-data consent/);
  } finally { await cleanup(); }
});

test("withdrawn consent never hides an injury that is already restricting training", async () => {
  const withInjury: TodayCommandView = {...NO_PLAN_STATE, open_injuries: [{id: "flag-1", athlete_id: "athlete-1",
    source: "checkin", body_area: "left knee", description: "sprain", severity: "moderate", status: "open",
    created_at: "2026-10-07T08:00:00Z", updated_at: "2026-10-07T08:00:00Z"}]};
  const {container, cleanup} = await renderToday(withInjury,
    {...CONSENTED, profile: {...CONSENTED.profile, health_consent_granted: false}});
  try {
    assert.ok(container.querySelector(".today-injury-item"));
    assert.doesNotMatch(container.textContent ?? "", /needs your health-data consent/);
  } finally { await cleanup(); }
});
