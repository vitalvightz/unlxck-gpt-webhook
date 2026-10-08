import test from "node:test";
import assert from "node:assert/strict";
import { window as domWindow } from "../test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { AchillesAssessmentForm } from "./achilles-assessment-form";
import type { InjuryFlagRecord } from "@/lib/types";
import type { InjuryEpisodeObservation } from "@/lib/api-schema.generated";

const injury: InjuryFlagRecord = { id: "injury-owned", athlete_id: "athlete-owned", episode_id: "episode-owned",
  side: "left", source: "checkin", body_area: "Left Achilles", description: "Achilles tendonitis", severity: "moderate",
  status: "monitoring", created_at: "2026-10-01T00:00:00Z", updated_at: "2026-10-01T00:00:00Z",
  rehab_decision: { outcome: "live_prescription", summary: "Current guidance", reason_codes: [], achilles_load_review: {
    criterion_id: "achilles_restore_load_review_v1", criterion_version: 1, status: "unknown", subtype: "unknown",
    reason_codes: [], required_input_ids: [], observation_id: null, externally_verified: false, promotion_allowed: false, sources: [],
  } },
};

async function mount(row = injury, options: { fail?: boolean; refreshFails?: boolean; disabled?: boolean } = {}) {
  const container = document.createElement("div"); document.body.appendChild(container);
  const root = createRoot(container);
  const calls: InjuryEpisodeObservation[] = [];
  const originalFetch = globalThis.fetch, originalFormData = globalThis.FormData;
  globalThis.FormData = domWindow.FormData;
  globalThis.fetch = (async (_input, init) => {
    calls.push(JSON.parse(String(init?.body)));
    return new Response(JSON.stringify(options.fail ? { detail: "Try again" } : { id: "saved" }),
      { status: options.fail ? 503 : 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  let refreshes = 0;
  await act(async () => root.render(<AchillesAssessmentForm injury={row} token="athlete-token" disabled={options.disabled}
    onRefresh={async () => { refreshes += 1; if (options.refreshFails) throw new Error("Offline"); }} />));
  const set = (name: string, value: string) => {
    const field = container.querySelector<HTMLInputElement | HTMLSelectElement>(`[name="${name}"]`);
    assert.ok(field, name); field.value = value;
  };
  const submit = async () => {
    await act(async () => { container.querySelector("form")!.dispatchEvent(new domWindow.Event("submit", { bubbles: true, cancelable: true })); });
  };
  return { container, calls, set, submit, refreshes: () => refreshes,
    cleanup: () => { act(() => root.unmount()); container.remove(); globalThis.fetch = originalFetch; globalThis.FormData = originalFormData; } };
}

test("unknown inputs save through the owned shared API without claiming verification or readiness", async () => {
  const ui = await mount();
  try {
    ui.set("assessed_at", "2026-10-05T12:00"); await ui.submit();
    assert.equal(ui.calls.length, 1);
    const body = ui.calls[0];
    assert.equal(body.event_type, "rehab_progression_assessment");
    assert.equal(body.injury_id, injury.id); assert.equal(body.injury_episode_id, injury.episode_id);
    assert.equal(body.assessment?.side, "left"); assert.equal(body.assessment?.payload.site, "unknown");
    assert.equal(body.assessment?.payload.suspected_rupture, null);
    assert.equal(body.assessment?.payload.delayed_symptoms, null);
    assert.ok(!("externally_verified" in body.assessment!));
    assert.equal(ui.refreshes(), 1);
    assert.match(ui.container.querySelector('[role="status"]')?.textContent ?? "", /Loading rehab stays locked/);
    assert.equal(ui.container.querySelector('[name="side"]'), null);
  } finally { ui.cleanup(); }
});

test("actual clinician-attributed observations and exact measurements remain an athlete report", async () => {
  const ui = await mount();
  try {
    for (const [name, value] of Object.entries({ assessed_at: "2026-10-05T12:00", assessor: "clinician_physio", site: "insertional",
      incompatible_pathology: "excluded", heel_rise_completed: "yes", heel_rise_mode: "single_leg", heel_rise_quality: "controlled",
      heel_rise_repetitions: "4", heel_rise_assessor_usable: "yes", loading_task: "heel_rise_assessment",
      loading_performed_at: "2026-10-04T12:00", during_symptoms: "0", delayed_symptoms: "2", delayed_response_at: "2026-10-05T12:00",
      range_assessed: "yes", permitted_range: "floor_level", resistance: "external", resistance_kg: "5.5",
      range_load_tolerance: "tolerated", range_load_assessor_usable: "yes", clinician_restriction: "no" })) ui.set(name, value);
    await ui.submit();
    assert.equal(ui.calls[0].assessment?.assessor, "clinician_physio");
    assert.equal(ui.calls[0].assessment?.payload.during_symptoms, 0);
    assert.equal(ui.calls[0].assessment?.payload.heel_rise_repetitions, 4);
    assert.equal(ui.calls[0].assessment?.payload.resistance_kg, 5.5);
    assert.match(ui.container.textContent ?? "", /not verified/);
  } finally { ui.cleanup(); }
});

test("unchanged failed writes retry with the same report ID, changed snapshots get a new ID", async () => {
  const ui = await mount(injury, { fail: true });
  try {
    ui.set("assessed_at", "2026-10-05T12:00"); await ui.submit(); await ui.submit();
    assert.equal(ui.calls[0].report_id, ui.calls[1].report_id); assert.equal(ui.refreshes(), 0);
    ui.set("site", "midportion"); await ui.submit();
    assert.notEqual(ui.calls[2].report_id, ui.calls[1].report_id);
    assert.equal(ui.container.querySelector('[role="status"]'), null);
    assert.match(ui.container.querySelector('[role="alert"]')?.textContent ?? "", /Try again/);
  } finally { ui.cleanup(); }
});

test("a persisted report is still acknowledged when refresh fails", async () => {
  const ui = await mount(injury, { refreshFails: true });
  try {
    ui.set("assessed_at", "2026-10-05T12:00"); await ui.submit();
    assert.match(ui.container.querySelector('[role="status"]')?.textContent ?? "", /saved/);
    assert.match(ui.container.querySelector('[role="alert"]')?.textContent ?? "", /report was saved/);
  } finally { ui.cleanup(); }
});

for (const [name, changes] of Object.entries({ wrongProfile: { rehab_decision: null }, noEpisode: { episode_id: null },
  resolved: { status: "resolved" as const }, unknownSide: { side: "unknown" as const } })) {
  test(`${name} cannot offer an attributable assessment write`, async () => {
    const ui = await mount({ ...injury, ...changes });
    try { assert.equal(ui.container.querySelector("form"), null); assert.equal(ui.calls.length, 0); } finally { ui.cleanup(); }
  });
}

test("unknown completion cannot silently discard supplied functional results", async () => {
  const ui = await mount();
  try {
    ui.set("assessed_at", "2026-10-05T12:00"); ui.set("heel_rise_repetitions", "4"); await ui.submit();
    assert.equal(ui.calls.length, 0); assert.match(ui.container.textContent ?? "", /need a completed assessment/);
  } finally { ui.cleanup(); }
});

test("delayed ratings require actual observation times, never a fabricated next-day measurement", async () => {
  const ui = await mount();
  try {
    ui.set("assessed_at", "2026-10-05T12:00"); ui.set("delayed_symptoms", "2"); await ui.submit();
    assert.equal(ui.calls.length, 0); assert.match(ui.container.textContent ?? "", /observation time for each symptom rating/);
  } finally { ui.cleanup(); }
});

test("coach observations cannot claim clinician pathology exclusion", async () => {
  const ui = await mount();
  try {
    ui.set("assessed_at", "2026-10-05T12:00"); ui.set("assessor", "coach_observed"); ui.set("incompatible_pathology", "excluded");
    await ui.submit(); assert.equal(ui.calls.length, 0); assert.match(ui.container.textContent ?? "", /Only record pathology exclusion/);
  } finally { ui.cleanup(); }
});
