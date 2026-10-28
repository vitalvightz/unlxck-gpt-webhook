import assert from "node:assert/strict";
import test from "node:test";
import { window } from "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { SessionDetails, type SessionDetailsCache } from "./session-details";
import type { TrainingHistorySession } from "@/lib/training-history";
import { SHEET_EXIT_MS } from "@/lib/use-sheet-exit";

const proto = window.HTMLDialogElement.prototype;
proto.showModal ??= function () { this.setAttribute("open", ""); };
proto.close ??= function () { this.removeAttribute("open"); };
const row: TrainingHistorySession = { id: "one", source: "unlxck", title: "Strength", training_day: "2026-10-10",
  status: "done", activity: null, plan_id: "old-plan", duration_minutes: null, effort: null };
const payload = { session: row, prescription_source: "snapshot", blocks: [
  { name: "Squat", kind: "exercise", prescribed: { sets: 4, reps: 6 }, actual: {}, status: null, responses: [] },
  { name: "Calf raise", kind: "rehab", prescribed: { sets: 3, reps: 10 }, actual: {}, status: "stopped", responses: [], completed_dose: { completion_state: "partial_amount_unknown" } },
] };

test("details distinguish unknown actuals, reuse visit cache, and dismiss with Escape", async () => {
  const fetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => { calls++; return new Response(JSON.stringify(payload)); };
  const cache: SessionDetailsCache = new Map();
  const container = document.createElement("div"); document.body.append(container);
  const trigger = document.createElement("button"); document.body.append(trigger); trigger.focus();
  const root = createRoot(container); let dismissed = false;
  const render = () => root.render(<SessionDetails row={row} token="token" cache={cache} onDismiss={() => { dismissed = true; }} />);
  try {
    await act(async () => render());
    assert.match(container.textContent!, /Performed values unknown/);
    assert.match(container.textContent!, /Completed amount unknown/);
    assert.equal(container.querySelectorAll("ol > li").length, 2);
    const dialog = container.querySelector("dialog")!;
    await act(async () => dialog.dispatchEvent(new window.Event("cancel", { bubbles: true, cancelable: true })));
    // The sheet slides away before it is dismissed.
    await act(async () => { await new Promise(resolve => setTimeout(resolve, SHEET_EXIT_MS + 20)); });
    assert.ok(dismissed);
    await act(async () => root.render(null));
    assert.equal(document.activeElement, trigger);
    await act(async () => render());
    assert.equal(calls, 1);
  } finally { act(() => root.unmount()); container.remove(); trigger.remove(); globalThis.fetch = fetch; }
});

test("failed details have a working retry and never cache the failure", async () => {
  const fetch = globalThis.fetch; let calls = 0;
  globalThis.fetch = async () => ++calls === 1 ? new Response("unavailable", { status: 503 }) : new Response(JSON.stringify(payload));
  const cache: SessionDetailsCache = new Map();
  const container = document.createElement("div"); document.body.append(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<SessionDetails row={row} token="token" cache={cache} onDismiss={() => {}} />));
    assert.match(container.querySelector('[role="alert"]')!.textContent!, /Unable to load/);
    assert.equal(cache.size, 0);
    await act(async () => container.querySelector<HTMLButtonElement>(".secondary-button")!.click());
    assert.equal(calls, 2);
    assert.match(container.textContent!, /Squat/);
  } finally { act(() => root.unmount()); container.remove(); globalThis.fetch = fetch; }
});

test("completed-as-prescribed blocks start collapsed and never repeat matching reported values", async () => {
  const fetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ ...payload, blocks: [
    { name: "Bound", kind: "exercise", prescribed: { sets: 4, reps: 2 }, actual: { sets: 4, set_entries: [{ reps: 2 }, { reps: 2 }, { reps: 2 }, { reps: 2 }] }, status: "as_prescribed", responses: [] },
    { name: "Press", kind: "exercise", prescribed: { sets: 3, reps: 5 }, actual: { sets: 2, reps: 5 }, status: "modified", responses: [] },
  ] }));
  const container = document.createElement("div"); document.body.append(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<SessionDetails row={row} token="token" cache={new Map()} onDismiss={() => {}} />));
    const toggles = [...container.querySelectorAll<HTMLButtonElement>("ol button[aria-expanded]")];
    assert.deepEqual(toggles.map(button => button.getAttribute("aria-expanded")), ["false", "true"]);
    assert.match(container.textContent!, /4 × 2/);
    const press = container.querySelector('[aria-label="Performance: Press"]')!;
    // Done beside planned on one row, with the changed value marked.
    assert.match(press.textContent!, /Sets2 \/ 3/);
    assert.ok(press.querySelector("[data-changed]"));
    await act(async () => toggles[0].click());
    assert.equal(container.querySelector('[aria-label="Performance: Bound"]'), null);
    assert.match(container.textContent!, /Completed as prescribed · reported values match/);
  } finally { act(() => root.unmount()); container.remove(); globalThis.fetch = fetch; }
});
