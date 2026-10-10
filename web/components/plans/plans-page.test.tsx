import assert from "node:assert/strict";
import test from "node:test";
import { window } from "../test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { NextIntlClientProvider } from "next-intl";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";
import { PathnameContext, SearchParamsContext } from "next/dist/shared/lib/hooks-client-context.shared-runtime";

import messages from "../../messages/en.json";
import PlansPage from "../../app/plans/page";
import { AppSessionContext } from "../auth-provider";
import { ToastProvider } from "../toast-provider";
import type { MeResponse, PlanSummary } from "@/lib/types";

function isoInDays(days: number): string {
  const date = new Date(Date.now() + days * 86_400_000);
  return date.toISOString().slice(0, 10);
}

function plan(id: string, overrides: Partial<PlanSummary> = {}): PlanSummary {
  return {
    plan_id: id,
    athlete_id: "athlete-1",
    full_name: "King",
    fight_date: isoInDays(30),
    technical_style: ["boxing"],
    created_at: "2026-10-07T18:21:00Z",
    status: "ready",
    activation_state: "eligible",
    ...overrides,
  };
}

type Call = { url: string; method: string; body: string | null };

async function mountPlans(plans: PlanSummary[], activeId: string | null) {
  const calls: Call[] = [];
  const originalFetch = globalThis.fetch;
  const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
  globalThis.fetch = (async (input: string, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: typeof init?.body === "string" ? init.body : null });
    if (url.endsWith("/api/plans/active")) {
      return activeId ? json(plans.find((item) => item.plan_id === activeId)) : json({ detail: "none" }, 404);
    }
    if (url.endsWith("/api/plans") && method === "GET") return json(plans);
    if (url.endsWith("/api/today")) return json({ active_plan: { id: activeId, phase: "GPP" } });
    if (method === "PATCH") {
      const name = JSON.parse(String(init?.body ?? "{}")).plan_name;
      return json({ ...plans.find((item) => url.endsWith(item.plan_id)), plan_name: name });
    }
    if (method === "DELETE") return new Response(null, { status: 204 });
    return json({});
  }) as typeof fetch;

  const me = {
    profile: { athlete_id: "athlete-1", full_name: "King", role: "athlete", access_status: "approved",
      technical_style: ["boxing"], tactical_style: ["pressure_fighter"] },
    latest_intake: null,
    plan_count: plans.length,
  } as unknown as MeResponse;
  const router = { push() {}, replace() {}, refresh() {}, back() {}, forward() {}, prefetch() {}, bfcacheId: "fixture" };
  const session = { isReady: true, isMeHydrated: true, hasTransientMeError: false,
    session: { access_token: "fixture-token" }, me, previewAppearanceMode() {}, refreshMe: async () => {},
    replaceMe() {}, signOut: async () => {} };
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => root.render(
    <NextIntlClientProvider locale="en" timeZone="Europe/London" messages={messages}>
      <AppRouterContext.Provider value={router}>
        <PathnameContext.Provider value="/plans"><SearchParamsContext.Provider value={new URLSearchParams()}>
          <AppSessionContext.Provider value={session}>
            <ToastProvider><PlansPage /></ToastProvider>
          </AppSessionContext.Provider>
        </SearchParamsContext.Provider></PathnameContext.Provider>
      </AppRouterContext.Provider>
    </NextIntlClientProvider>,
  ));
  // Let the plan list, active plan and Today phase requests settle.
  for (let i = 0; i < 5; i += 1) {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  }
  const click = async (element: Element | null | undefined) => {
    assert.ok(element);
    await act(async () => { (element as HTMLElement).click(); });
    for (let i = 0; i < 3; i += 1) {
      await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
    }
  };
  const cleanup = async () => {
    await act(async () => root.unmount());
    host.remove();
    globalThis.fetch = originalFetch;
  };
  return { host, calls, click, cleanup };
}

function buttonByText(scope: ParentNode, text: string): HTMLButtonElement | undefined {
  return [...scope.querySelectorAll<HTMLButtonElement>("button")].find((item) => item.textContent?.trim() === text);
}

function openDialog(): HTMLElement | null {
  const dialogs = document.querySelectorAll<HTMLElement>('[role="dialog"]');
  return dialogs[dialogs.length - 1] ?? null;
}

test("the current camp shows once: one status, the fight date once, a countdown and one way in", async () => {
  const active = plan("active-1");
  const view = await mountPlans([active, plan("old-1"), plan("old-2", { created_at: "2026-10-07T01:25:00Z" })], "active-1");
  try {
    const text = view.host.textContent ?? "";
    assert.equal(view.host.querySelector("h1")?.textContent, "Training plan");
    assert.match(text, /Current camp/);
    assert.match(text, /Fight camp/);
    assert.match(text, /D-(29|30|31)/);
    assert.match(text, /Until fight/);
    assert.match(text, /Pressure Fighter/);
    assert.match(text, /General prep/);
    // No more stacked status labels or a repeated fight date on the card.
    assert.doesNotMatch(text, /READY TO TRAIN|Ready to train|Intake ready|Current snapshot/i);
    const card = view.host.querySelector("article");
    assert.equal(card?.textContent?.match(/Active/g)?.length, 1);
    // One primary action; the rest are quiet.
    assert.equal(view.host.querySelectorAll("article .cta").length, 1);
    assert.match(text, /Previous plans/);
    assert.match(text, /2 saved/);
    assert.equal(view.host.querySelectorAll('ul button[aria-haspopup="dialog"]').length, 2);
  } finally {
    await view.cleanup();
  }
});

test("an open plan without a fight date shows no countdown", async () => {
  const view = await mountPlans([plan("open-1", { fight_date: "" })], "open-1");
  try {
    assert.doesNotMatch(view.host.textContent ?? "", /D-\d+|Until fight/);
    assert.match(view.host.textContent ?? "", /Open training plan/);
  } finally {
    await view.cleanup();
  }
});

test("management lives in a sheet: make active only for an eligible saved plan, rename and archive call the API", async () => {
  const view = await mountPlans(
    [plan("active-1"), plan("old-1"), plan("past-1", { activation_state: "fight_date_passed" })],
    "active-1",
  );
  try {
    // The page itself carries no Activate / Rename / Archive buttons.
    assert.equal(buttonByText(view.host, "Make active"), undefined);
    assert.equal(buttonByText(view.host, "Rename"), undefined);

    const rows = [...view.host.querySelectorAll<HTMLButtonElement>('ul button[aria-haspopup="dialog"]')];
    await view.click(rows[0]);
    let sheet = openDialog();
    assert.ok(sheet);
    assert.ok(buttonByText(sheet, "Make active"));
    await view.click(sheet.querySelector('button[aria-label="Close"]'));

    await view.click(rows[1]);
    sheet = openDialog();
    assert.equal(buttonByText(sheet!, "Make active"), undefined, "a passed camp can't be made active");
    await view.click(sheet!.querySelector('button[aria-label="Close"]'));

    // The current camp's Manage opens the same sheet, without Make active.
    await view.click(buttonByText(view.host, "Manage"));
    sheet = openDialog();
    assert.equal(buttonByText(sheet!, "Make active"), undefined);

    await view.click(buttonByText(sheet!, "Rename"));
    const input = sheet!.querySelector<HTMLInputElement>("input");
    assert.ok(input);
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!;
      setter.call(input, "Title fight");
      input.dispatchEvent(new window.Event("input", { bubbles: true }));
    });
    await view.click(buttonByText(sheet!, "Save"));
    const patch = view.calls.find((call) => call.method === "PATCH");
    assert.ok(patch?.url.endsWith("/api/plans/active-1"));
    assert.match(patch?.body ?? "", /Title fight/);

    await view.click(buttonByText(sheet!, "Archive"));
    await view.click(buttonByText(openDialog()!, "Archive"));
    assert.ok(view.calls.some((call) => call.method === "DELETE" && call.url.endsWith("/api/plans/active-1")));
  } finally {
    await view.cleanup();
  }
});

test("the athlete profile is one line that opens its details", async () => {
  const view = await mountPlans([plan("active-1")], "active-1");
  try {
    const row = buttonByText(view.host, "Athlete profileKing · Boxing · Pressure Fighter");
    assert.ok(row, view.host.textContent ?? "");
    await view.click(row);
    const sheet = openDialog();
    assert.match(sheet?.textContent ?? "", /Tactical style/);
    assert.match(sheet?.textContent ?? "", /Complete Advanced Intake/);
  } finally {
    await view.cleanup();
  }
});
