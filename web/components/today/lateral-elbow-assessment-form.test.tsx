import test from "node:test";
import assert from "node:assert/strict";
import { window as domWindow } from "../test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { LateralElbowAssessmentForm } from "./lateral-elbow-assessment-form";
import type { InjuryFlagRecord } from "@/lib/types";
import type { InjuryEpisodeObservation } from "@/lib/api-schema.generated";

const injury: InjuryFlagRecord = { id: "elbow-owned", athlete_id: "athlete-owned", episode_id: "episode-owned", side: "left",
  source: "checkin", body_area: "Left elbow", description: "Lateral elbow tendonitis", severity: "moderate", status: "monitoring",
  created_at: "2026-09-01T00:00:00Z", updated_at: "2026-09-01T00:00:00Z" };

async function mount(refreshFails = false, row = injury) {
  const container = document.createElement("div"); document.body.appendChild(container);
  const root = createRoot(container), calls: InjuryEpisodeObservation[] = [];
  const oldFetch = globalThis.fetch, oldFormData = globalThis.FormData;
  globalThis.FormData = domWindow.FormData;
  globalThis.fetch = (async (_input, init) => {
    calls.push(JSON.parse(String(init?.body)));
    return new Response("{}", { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  await act(async () => root.render(<LateralElbowAssessmentForm injury={row} token="test-token"
    onRefresh={async () => { if (refreshFails) throw new Error("Refresh offline"); }} />));
  function set(name: string, value: string) {
    const field = container.querySelector<HTMLInputElement | HTMLSelectElement>(`[name="${name}"]`);
    assert.ok(field, name); field.value = value;
  }
  async function submit() { await act(async () => container.querySelector("form")!.dispatchEvent(new domWindow.Event("submit", { bubbles: true, cancelable: true }))); }
  return { container, calls, set, submit, cleanup() {
    act(() => root.unmount()); container.remove(); globalThis.fetch = oldFetch; globalThis.FormData = oldFormData;
  } };
}

test("occasional elbow assessment uses the owned shared endpoint with honest unknown defaults", async () => {
  const ui = await mount();
  try {
    assert.equal(ui.container.querySelector("details")?.open, false);
    assert.match(ui.container.textContent ?? "", /self-reported, not independently verified/);
    ui.set("assessed_at", "2026-10-05T12:00"); await ui.submit();
    const body = ui.calls[0];
    assert.equal(body.event_type, "rehab_progression_assessment");
    assert.equal(body.injury_id, injury.id); assert.equal(body.injury_episode_id, injury.episode_id);
    assert.equal(body.assessment?.side, "left");
    assert.ok(body.assessment && "subtype" in body.assessment.payload);
    assert.equal(body.assessment.payload.subtype, "unknown");
    assert.equal(body.assessment.payload.grip_task, "unknown");
    assert.equal(body.assessment.payload.option_recommended, null);
    assert.ok(!("externally_verified" in body.assessment));
    assert.equal(ui.container.querySelector('[name="side"]'), null);
    assert.equal(ui.container.querySelectorAll('input[type="number"]').length, 0);
  } finally { ui.cleanup(); }
});

test("reported observations identify real tasks and retry identity survives refresh failure", async () => {
  const ui = await mount(true);
  try {
    for (const [name, value] of Object.entries({ assessed_at: "2026-10-05T12:00", subtype: "lateral", course: "chronic",
      safety_screen: "clear", pain_irritability: "acceptable", elbow_wrist_motion: "acceptable", grip_function: "acceptable",
      wrist_extension_tolerance: "acceptable", option_recommended: "yes" })) ui.set(name, value);
    await ui.submit(); await ui.submit();
    assert.equal(ui.calls[0].report_id, ui.calls[1].report_id);
    assert.ok(ui.calls[0].assessment && "grip_task" in ui.calls[0].assessment.payload);
    assert.equal(ui.calls[0].assessment.payload.grip_task, "daily_grip_task");
    assert.equal(ui.calls[0].assessment.payload.wrist_extension_task, "supported_hand_weight");
    assert.equal(ui.calls[0].assessment.payload.option_recommended, true);
    assert.match(ui.container.querySelector('[role="status"]')?.textContent ?? "", /report saved/);
    ui.set("grip_function", "unknown"); await ui.submit();
    assert.notEqual(ui.calls[1].report_id, ui.calls[2].report_id);
  } finally { ui.cleanup(); }
});

test("assessment refuses a future date and is unavailable for unknown side", async () => {
  const ui = await mount();
  try {
    ui.set("assessed_at", "2099-01-01T12:00"); await ui.submit();
    assert.equal(ui.calls.length, 0);
    assert.match(ui.container.querySelector('[role="alert"]')?.textContent ?? "", /up to now/);
  } finally { ui.cleanup(); }
  const unknown = await mount(false, { ...injury, side: "unknown" });
  try { assert.equal(unknown.container.querySelector("form"), null); } finally { unknown.cleanup(); }
});
