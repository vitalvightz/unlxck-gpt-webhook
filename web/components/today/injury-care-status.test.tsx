import test from "node:test";
import assert from "node:assert/strict";
import { window as domWindow } from "../test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { InjuryCareStatus, DelayedRehabResponse } from "./injury-care-status";
import type { InjuryFlagRecord } from "@/lib/types";

const injury: InjuryFlagRecord = {
  id: "injury-1", episode_id: "episode-1", athlete_id: "athlete-1", source: "checkin",
  body_area: "Chest", description: "Chest strain", severity: "mild", status: "open",
  surface_class: "non_surface", created_at: "", updated_at: "",
  rehab_decision: { outcome: "prescribed_rehab", summary: "Comfortable movement is available.", reason_codes: [],
    prescription: { sources: ["https://www.nhs.uk/conditions/sprains-and-strains/"] },
    schedule: { state: "recovery_day", reason: "Allow the recovery gap.", next_due_day: "2026-10-02" } },
};

async function click(container: HTMLElement, label: string) {
  const button = Array.from(container.querySelectorAll("button")).find(b => b.textContent === label);
  assert.ok(button, label);
  await act(async () => { button.dispatchEvent(new domWindow.MouseEvent("click", { bubbles: true })); });
}

test("clinician clearance is a quick scoped report without changing injury resolution", async () => {
  const container = document.createElement("div"); document.body.appendChild(container);
  const root = createRoot(container);
  const original = globalThis.fetch;
  const calls: Array<Record<string, unknown>> = [];
  let refreshes = 0;
  globalThis.fetch = (async (_input, init) => {
    calls.push(JSON.parse(String(init?.body)));
    return new Response("{}", { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  try {
    await act(async () => { root.render(<InjuryCareStatus injury={injury} token="token" onRefresh={async () => { refreshes++; }} />); });
    assert.match(container.textContent ?? "", /Recovery day/);
    assert.match(container.textContent ?? "", /Next due: 2026-10-02/);
    assert.equal(container.querySelector("a")?.getAttribute("href"), "https://www.nhs.uk/conditions/sprains-and-strains/");
    await click(container, "My clinician cleared me");
    assert.match(container.textContent ?? "", /does not unlock rehab or change its schedule/);
    await click(container, "Training without contact");
    assert.match(String(calls[0].report_id), /^[a-f0-9-]{36}$/);
    const { report_id: firstReportId, ...body } = calls[0];
    assert.deepEqual(body, { injury_id: "injury-1", injury_episode_id: "episode-1", event_type: "clinician_clearance_report", scopes: ["rehab", "training"] });
    assert.equal(refreshes, 1);
    await click(container, "My clinician cleared me");
    await click(container, "Training without contact");
    assert.notEqual(calls[1].report_id, firstReportId);
    assert.equal(container.querySelector('input[type="file"]'), null);
  } finally { globalThis.fetch = original; act(() => root.unmount()); container.remove(); }
});

test("next-day uncertainty is saved separately from the during response", async () => {
  const container = document.createElement("div"); document.body.appendChild(container);
  const root = createRoot(container);
  const original = globalThis.fetch;
  const calls: Array<Record<string, unknown>> = [];
  globalThis.fetch = (async (_input, init) => {
    calls.push(JSON.parse(String(init?.body)));
    return new Response("{}", { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  try {
    await act(async () => { root.render(<DelayedRehabResponse token="token" onRefresh={async () => {}} prompt={{
      exposure_id: "exposure-1", injury_id: "injury-1", injury_episode_id: "episode-1", region: "chest",
      question: "How did this injury feel the day after rehab?", options: ["better", "same", "worse", "not_sure"],
    }} />); });
    await click(container, "Not sure");
    assert.equal(calls[0].event_type, "delayed_rehab_response");
    assert.equal(calls[0].response, "not_sure");
    assert.equal(calls[0].exposure_id, "exposure-1");
    assert.match(container.textContent ?? "", /response saved/);
  } finally { globalThis.fetch = original; act(() => root.unmount()); container.remove(); }
});
