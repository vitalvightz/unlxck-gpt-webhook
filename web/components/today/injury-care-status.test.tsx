import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { window as domWindow } from "../test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { InjuryCareStatus, DelayedRehabResponse, EffectiveClinicianClearanceStatus } from "./injury-care-status";
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

for (const [label, scopes] of [
  ["Rehab only", ["rehab"]],
  ["Train, no contact", ["rehab", "training"]],
  ["Train + contact", ["rehab", "training", "contact"]],
] as const) {
  test(`clinician clearance submits unchanged scopes for ${label}`, async () => {
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
      await click(container, "Report clinician clearance");
      assert.match(container.textContent ?? "", /does not override safety guidance or advance rehab/);
      assert.equal(container.querySelectorAll(".today-segment-row > .today-segment").length, 3);
      await click(container, label);
      assert.match(String(calls[0].report_id), /^[a-f0-9-]{36}$/);
      const { report_id: firstReportId, ...body } = calls[0];
      assert.deepEqual(body, { injury_id: "injury-1", injury_episode_id: "episode-1", event_type: "clinician_clearance_report", scopes });
      assert.equal(refreshes, 1);
      await click(container, "Report clinician clearance");
      assert.equal(container.querySelectorAll(".today-segment-row > .today-segment").length, 3);
      await click(container, label);
      assert.notEqual(calls[1].report_id, firstReportId);
      assert.equal(container.querySelector('input[type="file"]'), null);
    } finally { globalThis.fetch = original; act(() => root.unmount()); container.remove(); }
  });
}

for (const response of ["better", "same", "worse", "not_sure"] as const) {
  test(`next-day ${response} is saved separately from the during response`, async () => {
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
      assert.equal(container.querySelectorAll(".today-segment-row > .today-segment").length, 4);
      await click(container, { better: "Better", same: "Same", worse: "Worse", not_sure: "Not sure" }[response]);
      assert.equal(calls[0].event_type, "delayed_rehab_response");
      assert.deepEqual(calls[0], {
        injury_id: "injury-1", injury_episode_id: "episode-1", event_type: "delayed_rehab_response",
        exposure_id: "exposure-1", response,
      });
      assert.equal(calls[0].exposure_id, "exposure-1");
      assert.match(container.textContent ?? "", /response saved/);
    } finally { globalThis.fetch = original; act(() => root.unmount()); container.remove(); }
  });
}

test("clearance retry keeps the report identity when refresh fails after saving", async () => {
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
    await act(async () => { root.render(<InjuryCareStatus injury={injury} token="token" onRefresh={async () => {
      if (++refreshes === 1) throw new Error("Refresh failed");
    }} />); });
    await click(container, "Report clinician clearance");
    await click(container, "Rehab only");
    assert.match(container.textContent ?? "", /Refresh failed/);
    await click(container, "Rehab only");
    assert.equal(calls.length, 2);
    assert.equal(calls[0].report_id, calls[1].report_id);
  } finally { globalThis.fetch = original; act(() => root.unmount()); container.remove(); }
});

test("unsupported guidance shows a repeated reason only once and keeps schedule state", () => {
  const summary = "No suitable rehab is available for this injury yet. Keep to your current restrictions.";
  for (const reason of [summary, "A separate schedule reason."]) {
    const html = renderToStaticMarkup(<InjuryCareStatus injury={{ ...injury, rehab_decision: {
      outcome: "unsupported_prescription", summary, reason_codes: [],
      schedule: { state: "unsupported", reason },
    } }} token="token" onRefresh={async () => {}} />);
    assert.equal(html.split(summary).length - 1, 1);
    assert.match(html, /Guidance unavailable/);
    if (reason !== summary) assert.ok(html.includes(reason));
  }
});

for (const [scopes, label] of [
  [["rehab"], "Rehab only"],
  [["rehab", "training"], "Train, no contact"],
  [["rehab", "training", "contact"], "Train + contact"],
] as const) {
  test(`current clearance shows ${label} and an update action`, () => {
    const html = renderToStaticMarkup(<InjuryCareStatus injury={{ ...injury, clinician_clearance: {
      episode_id: injury.episode_id!, scopes: [...scopes], source: "athlete_reported", externally_verified: false,
    } }} token="token" onRefresh={async () => {}} />);
    assert.ok(html.includes(`Reported clearance for this injury: ${label}`));
    assert.ok(html.includes("Update clinician clearance"));
    assert.ok(!html.includes("Report clinician clearance"));
  });
}

test("updating clearance displays the refreshed scope, and worsening removes current clearance", async () => {
  const container = document.createElement("div"); document.body.appendChild(container);
  const root = createRoot(container);
  const original = globalThis.fetch;
  let current: InjuryFlagRecord = { ...injury, clinician_clearance: {
    episode_id: injury.episode_id!, scopes: ["rehab", "training"], source: "athlete_reported", externally_verified: false,
  } };
  const calls: Array<Record<string, unknown>> = [];
  const render = () => root.render(<InjuryCareStatus injury={current} token="token" onRefresh={async () => {
    render();
  }} />);
  globalThis.fetch = (async (_input, init) => {
    const body = JSON.parse(String(init?.body)); calls.push(body);
    current = { ...current, clinician_clearance: { ...current.clinician_clearance!, scopes: body.scopes } };
    return new Response("{}", { status: 200 });
  }) as typeof fetch;
  try {
    await act(async () => { render(); });
    assert.match(container.textContent ?? "", /Reported clearance for this injury: Train, no contact/);
    await click(container, "Update clinician clearance");
    await click(container, "Train + contact");
    assert.deepEqual(calls[0].scopes, ["rehab", "training", "contact"]);
    assert.equal(calls[0].event_type, "clinician_clearance_report");
    assert.ok(!("status" in calls[0]));
    assert.equal(current.status, "open");
    assert.match(container.textContent ?? "", /Reported clearance for this injury: Train \+ contact/);
    assert.doesNotMatch(container.textContent ?? "", /Reported clearance for this injury: Train, no contact/);
    current = { ...current, clinician_clearance: null, latest_reported_status: "worse" };
    await act(async () => { render(); });
    assert.doesNotMatch(container.textContent ?? "", /Reported clearance for this injury:|Update clinician clearance/);
    assert.match(container.textContent ?? "", /Report clinician clearance/);
  } finally { globalThis.fetch = original; act(() => root.unmount()); container.remove(); }
});

test("no current clearance uses the report action without claiming a current scope", () => {
  const html = renderToStaticMarkup(<InjuryCareStatus injury={injury} token="token" onRefresh={async () => {}} />);
  assert.ok(html.includes("Report clinician clearance"));
  assert.ok(!html.includes("Reported clearance for this injury:"));
});


for (const scopes of [["contact"], ["training"], ["rehab", "contact"], [], ["rehab", "rehab"]] as const) {
  test(`noncanonical clearance ${scopes.join(",")} never displays a training grant`, () => {
    const html = renderToStaticMarkup(<InjuryCareStatus injury={{ ...injury, clinician_clearance: {
      episode_id: injury.episode_id!, scopes: [...scopes], source: "athlete_reported", externally_verified: false,
    } }} token="token" onRefresh={async () => {}} />);
    assert.match(html, /Reported clearance for this injury: Scope unclear/);
    assert.doesNotMatch(html, /Reported clearance for this injury: Train/);
  });
}

test("effective clearance remains authoritative above a permissive individual report", () => {
  const html = renderToStaticMarkup(<>
    <EffectiveClinicianClearanceStatus clearance={{ level: "rehab_only", scopes: ["rehab"], requires_update: false,
      limited_by: [{ injury_id: injury.id, injury_episode_id: injury.episode_id!, label: "Chest strain" }] }} />
    <InjuryCareStatus injury={{ ...injury, id: "ankle", clinician_clearance: {
      episode_id: injury.episode_id!, scopes: ["rehab", "training", "contact"], source: "athlete_reported", externally_verified: false,
    } }} token="token" onRefresh={async () => {}} />
  </>);
  assert.match(html, /<strong>Effective clinician clearance: Rehab only<\/strong>/);
  assert.match(html, /Limited by: Chest strain/);
  assert.match(html, /Reported clearance for this injury: Train \+ contact/);
  assert.doesNotMatch(html, /Effective clinician clearance: Train/);
});

test("unclear effective scope explains its conservative ceiling", () => {
  const html = renderToStaticMarkup(<EffectiveClinicianClearanceStatus clearance={{
    level: "rehab_only", scopes: ["rehab"], requires_update: true,
    limited_by: [{ injury_id: injury.id, injury_episode_id: injury.episode_id!, label: "Chest strain" }],
  }} />);
  assert.match(html, /Effective clinician clearance: Rehab only/);
  assert.match(html, /Rehab only until clarified/);
  assert.equal(renderToStaticMarkup(<EffectiveClinicianClearanceStatus clearance={null} />), "");
});
