import test from "node:test";
import assert from "node:assert/strict";

import "../test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";

import { AppSessionContext } from "@/components/auth-provider";
import { ToastProvider } from "@/components/toast-provider";
import { getAnalyticsPreference, setAnalyticsPreference } from "@/lib/api";
import type { SparringLogRecord } from "@/lib/types";

import { SparringLogPrompt, type SparringDraft } from "./sparring-log-prompt";
import { TodayReadinessForm } from "./today-readiness-form";

const DRAFT: SparringDraft = {
  source: "contact",
  planId: "plan-1",
  sessionId: null,
  plannedIntensity: "hard",
  title: "Hard sparring",
  rounds: 5,
  roundSeconds: 180,
};

/** Records event requests; the preference endpoint answers with `enabled`. */
async function withApi(enabled: Record<string, boolean>, run: (events: unknown[]) => Promise<void>) {
  const original = globalThis.fetch;
  const events: unknown[] = [];
  globalThis.fetch = async (input, init) => {
    const path = String(input);
    const token = String(new Headers(init?.headers).get("Authorization")).replace("Bearer ", "");
    if (path.endsWith("/api/analytics/preference")) {
      if (init?.method === "PUT") enabled[token] = JSON.parse(String(init.body)).enabled;
      return new Response(JSON.stringify({ enabled: enabled[token] ?? false }), { status: 200 });
    }
    if (path.endsWith("/api/analytics/events")) {
      events.push(JSON.parse(String(init?.body)));
      return new Response(JSON.stringify({ accepted: true }), { status: 202 });
    }
    return new Response("{}", { status: 500 });
  };
  try {
    await run(events);
  } finally {
    globalThis.fetch = original;
  }
}

async function mount(node: React.ReactNode) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const me = { profile: { health_consent_granted: true } };
  await act(async () =>
    root.render(
      <AppSessionContext.Provider value={{ session: null, me } as never}>
        <ToastProvider>{node}</ToastProvider>
      </AppSessionContext.Provider>,
    ),
  );
  return {
    container,
    unmount: () => {
      act(() => root.unmount());
      container.remove();
    },
  };
}

const flush = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });

test("a check-in's first answer records one start without any answer values", async () => {
  await withApi({ "checkin-on": true }, async (events) => {
    await getAnalyticsPreference("checkin-on");
    const view = await mount(<TodayReadinessForm token="checkin-on" onRefresh={async () => {}} />);
    try {
      assert.equal(events.length, 0, "showing the form is not a start");
      const poor = [...view.container.querySelectorAll("button")].find((b) => b.textContent === "Poor")!;
      const high = [...view.container.querySelectorAll("button")].find((b) => b.textContent === "High")!;
      await act(async () => poor.click());
      await act(async () => high.click());
      view.container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click();
      await flush();
      assert.equal(events.length, 1);
      const [event] = events as Record<string, unknown>[];
      assert.deepEqual(Object.keys(event).sort(), ["event_name", "feature", "request_id"]);
      assert.equal(event.event_name, "checkin_started");
      assert.equal(event.feature, "recovery");
      assert.doesNotMatch(JSON.stringify(event), /poor|high|sharp|pain|sleep/i);
    } finally {
      view.unmount();
    }
  });
});

test("beta check-in starts record without an optional choice", async () => {
  await withApi({}, async (events) => {
    await getAnalyticsPreference("checkin-declined");
    await setAnalyticsPreference("checkin-withdrawn", true);
    await setAnalyticsPreference("checkin-withdrawn", false);
    for (const token of ["checkin-declined", "checkin-withdrawn", "checkin-unloaded"]) {
      const view = await mount(<TodayReadinessForm token={token} onRefresh={async () => {}} />);
      try {
        const poor = [...view.container.querySelectorAll("button")].find((b) => b.textContent === "Poor")!;
        await act(async () => poor.click());
        await flush();
      } finally {
        view.unmount();
      }
    }
    assert.equal(events.length, 3);
  });
});

test("a new sparring log records a start; reopening a saved one does not", async () => {
  await withApi({ "spar-on": true }, async (events) => {
    await getAnalyticsPreference("spar-on");
    const opened = await mount(<SparringLogPrompt token="spar-on" draft={DRAFT} onDismiss={() => {}} />);
    await flush();
    opened.unmount();
    assert.deepEqual(
      (events as Record<string, unknown>[]).map((e) => [e.event_name, e.feature]),
      [["sparring_log_started", "sparring"]],
    );
    const existing = { intensity: "hard", rounds_completed: 5, head_contact: "none", rocked: false, notes: "", detail_revision: 1 } as unknown as SparringLogRecord;
    const reopened = await mount(<SparringLogPrompt token="spar-on" draft={{ ...DRAFT, existing }} onDismiss={() => {}} />);
    await flush();
    reopened.unmount();
    assert.equal(events.length, 1);
  });
});
