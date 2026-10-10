import assert from "node:assert/strict";
import test from "node:test";
import { window } from "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { TrainingLibrary } from "./training-library";
import type { LibraryEntry, LibrarySearchResponse } from "@/lib/api-schema.generated";

const entry: LibraryEntry = { catalogue_id: "stable-id", name: "Medicine Ball Hook Throw", category: "training", content_type: "strength_power",
  context: "Strength", equipment: ["medicine_ball"], equipment_state: "known", exercise_key: "medicine-ball-hook-throw", media: null,
  focus: ["Punching power"], discovery_match: null, selection_boundary: "training_validation_required", prescription_allowed: false };
const response = (overrides: Partial<LibrarySearchResponse> = {}): LibrarySearchResponse => ({ entries: [entry], total: 1, catalogue_total: 2855,
  offset: 0, limit: 24, next_offset: null, revision: "initial", facets: {}, ...overrides });
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const settle = async (ms = 10) => act(async () => { await new Promise(resolve => setTimeout(resolve, ms)); });

async function mount(fetcher: typeof fetch) {
  const original = globalThis.fetch;
  globalThis.fetch = fetcher;
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => root.render(<TrainingLibrary accessToken="token" />));
  await settle();
  const click = async (text: string) => {
    const button = Array.from(document.querySelectorAll("button")).find(item => item.textContent === text);
    assert.ok(button, text);
    await act(async () => button.click());
    await settle();
  };
  const input = async (text: string) => {
    const control = host.querySelector("input")!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!.call(control, text);
      control.dispatchEvent(new window.Event("input", { bubbles: true }));
    });
  };
  const cleanup = async () => { await act(async () => root.unmount()); host.remove(); globalThis.fetch = original; };
  return { host, click, input, cleanup };
}

test("Search debounces, aborts obsolete requests and refuses stale results", async () => {
  let stale: ((value: Response) => void) | undefined;
  let staleSignal: AbortSignal | null | undefined;
  const calls: string[] = [];
  const ui = await mount((async (input, init) => {
    const url = String(input); calls.push(url);
    if (url.includes("q=old")) { staleSignal = init?.signal; return new Promise(resolve => { stale = resolve; }); }
    return json(response());
  }) as typeof fetch);
  try {
    await ui.input("old"); await settle(220);
    assert.ok(stale);
    await ui.input("punching"); await ui.input("punching power"); await settle(220);
    assert.equal(staleSignal?.aborted, true);
    assert.equal(calls.filter(url => url.includes("q=punching&")).length, 0);
    await act(async () => stale!(json(response({ entries: [{ ...entry, name: "Stale result" }] }))));
    assert.ok(ui.host.textContent?.includes(entry.name));
    assert.ok(!ui.host.textContent?.includes("Stale result"));
  } finally { await ui.cleanup(); }
});

test("Pagination carries revision; a changed catalogue refreshes instead of mixing rows", async () => {
  const calls: string[] = [];
  const ui = await mount((async input => {
    const url = String(input); calls.push(url);
    if (url.includes("offset=")) return json({ detail: "Library changed. Refresh your search." }, 409);
    return json(response({ total: 25, next_offset: calls.length === 1 ? 24 : null }));
  }) as typeof fetch);
  try {
    await ui.click("Load more"); await settle();
    assert.ok(calls.some(url => url.includes("offset=24") && url.includes("revision=initial")));
    assert.equal(calls.length, 3);
    assert.equal(ui.host.querySelectorAll("li").length, 1);
    assert.ok(!ui.host.textContent?.includes("Load more"));
  } finally { await ui.cleanup(); }
});

test("Unavailable search removes stale drills; retry restores them", async () => {
  let fail = false;
  const ui = await mount((async () => fail ? json({ detail: "Unavailable" }, 503) : json(response())) as typeof fetch);
  try {
    fail = true;
    await ui.input("retry"); await settle(220);
    assert.equal(ui.host.querySelectorAll("li").length, 0);
    assert.ok(ui.host.querySelector('[role="alert"]')?.textContent?.includes("Unavailable"));
    fail = false;
    await ui.click("Retry search"); await settle(220);
    assert.equal(ui.host.querySelectorAll("li").length, 1);
  } finally { await ui.cleanup(); }
});
