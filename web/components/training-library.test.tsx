import assert from "node:assert/strict";
import test from "node:test";
import { window } from "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { TrainingLibrary } from "./training-library";
import type { LibraryEntry, LibrarySearchResponse } from "@/lib/api-schema.generated";

const entry: LibraryEntry = { catalogue_id: "stable-id", name: "Medicine Ball Hook Throw", category: "training", content_type: "strength_power",
  context: "Strength", equipment: ["medicine_ball"], equipment_state: "known", equipment_requirements: null, exercise_key: "medicine-ball-hook-throw", media: null,
  focus: ["Punching power"], verified_goals: ["Punching power"], exercise_details: [], discovery_match: null, selection_boundary: "training_validation_required", prescription_allowed: false, log_format: null };
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

test("Goal filter reaches the API and preview shows reviewed adaptation and execution", async () => {
  const calls: string[] = [];
  const ui = await mount((async input => {
    const url = String(input); calls.push(url);
    if (url.includes("/library/entry")) return json({ ...entry, focus: ["Coordination"], guidance: {},
      metadata_projection: [{ canonical_id: "coordination", label: "Coordination", status: "reviewed_goal",
        goal_evidence: { why: "Coordinate opposite hand-foot support.", cue: "Finish with a stable base." } }] });
    return json(response({ facets: { goal: [{ value: "Coordination", label: "Coordination", count: 24 }] } }));
  }) as typeof fetch);
  try {
    await ui.click("Filters");
    await act(async () => document.querySelector<HTMLButtonElement>('button[aria-label="Goal: Any"]')!.click());
    await act(async () => document.querySelector<HTMLButtonElement>('[data-value="Coordination"]')!.click());
    await settle();
    assert.ok(calls.some(url => url.includes("goal=Coordination")));
    await ui.click("Show results");
    const drill = ui.host.querySelector<HTMLButtonElement>("li button");
    assert.ok(drill);
    await act(async () => drill.click());
    await settle();
    assert.ok(document.body.textContent?.includes("Goal: Coordination"));
    assert.ok(document.body.textContent?.includes("Coordinate opposite hand-foot support."));
    assert.ok(document.body.textContent?.includes("Finish with a stable base."));
  } finally { await ui.cleanup(); }
});

test("Detailed browsing works without a Goal, clears chips and clears incompatible category filters", async () => {
  const calls: URL[] = [];
  const hold = { ...entry, catalogue_id: "hold", name: "Static stance hold", focus: [], verified_goals: [],
    exercise_details: [{ value: "static_holds", label: "Static holds", group: "training_method" as const },
      { value: "balance", label: "Balance work", group: "physical_focus" as const }] };
  const ui = await mount((async input => {
    const url = new URL(String(input), "http://localhost"); calls.push(url);
    if (url.pathname.endsWith("/entry")) return json({ ...hold, guidance: { Why: ["Coach detail"] }, metadata_projection: [] });
    const selected = url.searchParams.get("training_method") || url.searchParams.get("physical_focus");
    const empty = selected && url.searchParams.get("movement") || url.searchParams.get("q") === "missing";
    return json(response({ entries: empty ? [] : selected ? [hold] : [entry, hold], total: empty ? 0 : selected ? 1 : 2,
      facets: { training_method: [{ value: "static_holds", label: "Static holds", count: 1 }],
        movement: [{ value: "rotation", label: "Rotation", count: 1 }],
        physical_focus: [{ value: "balance", label: "Balance work", count: 1 }] } }));
  }) as typeof fetch);
  async function select(title: string, value: string) {
    const trigger = document.querySelector<HTMLButtonElement>(`button[aria-label^="${title}: "]`);
    assert.ok(trigger);
    await act(async () => trigger.click());
    const control = document.querySelector<HTMLButtonElement>(`button[data-value="${value}"]`);
    assert.ok(control);
    await act(async () => control.click());
    await settle();
  }
  try {
    assert.equal(ui.host.querySelectorAll("li").length, 2);
    await ui.click("Filters"); await select("Training method", "static_holds"); await ui.click("Show results");
    assert.equal(ui.host.querySelectorAll("li").length, 1);
    assert.ok(ui.host.textContent?.includes("Method: Static holds"));
    assert.equal(calls.at(-1)?.searchParams.get("goal"), null);
    const drill = ui.host.querySelector<HTMLButtonElement>("li button")!;
    assert.ok(drill.textContent?.includes("Static holds"));
    assert.ok(!drill.textContent?.includes("Goal:"));
    await act(async () => drill.click()); await settle();
    assert.ok(document.body.textContent?.includes("Exercise details"));
    assert.ok(document.body.querySelector("details")?.textContent?.includes("Coach detail"));
    await act(async () => document.querySelector<HTMLButtonElement>('[aria-label="Close drill preview"]')!.click()); await settle();
    await act(async () => ui.host.querySelector<HTMLButtonElement>('[aria-label="Remove Training method filter"]')!.click()); await settle();
    assert.equal(ui.host.querySelectorAll("li").length, 2);
    await ui.click("Filters"); await select("Training method", "static_holds"); await select("Movement", "rotation"); await ui.click("Show results");
    assert.ok(ui.host.textContent?.includes("No exercises match these filters."));
    assert.ok(ui.host.textContent?.includes("Movement: Rotation"));
    assert.ok(!ui.host.textContent?.includes("Clear one filter"));
    await ui.click("Clear all filters");
    assert.equal(ui.host.querySelectorAll("li").length, 2);
    await ui.input("missing"); await settle(220);
    assert.ok(ui.host.textContent?.includes("No exercises match your search."));
    assert.ok(!ui.host.textContent?.includes("No exercises match these filters."));
    await ui.click("Clear search");
    assert.equal(ui.host.querySelectorAll("li").length, 2);
    await ui.click("Filters"); await select("Physical focus", "balance"); await ui.click("Show results");
    assert.equal(ui.host.querySelectorAll("li").length, 1);
    assert.ok(ui.host.textContent?.includes("Physical focus: Balance work"));
    assert.ok(ui.host.querySelector('[aria-label="Remove Physical focus filter"]'));
    await act(async () => ui.host.querySelector<HTMLButtonElement>('[aria-label="Remove Physical focus filter"]')!.click()); await settle();
    assert.equal(ui.host.querySelectorAll("li").length, 2);
    await ui.click("Filters"); await select("Physical focus", "balance"); await ui.click("Show results");
    await ui.click("Rehab");
    assert.equal(calls.at(-1)?.searchParams.get("movement"), null);
    assert.equal(calls.at(-1)?.searchParams.get("training_method"), null);
    assert.equal(calls.at(-1)?.searchParams.get("physical_focus"), null);
    await ui.click("Filters");
    assert.ok(!document.body.textContent?.includes("Explore exercises"));
    assert.ok(!Array.from(document.querySelectorAll("label")).some(label => label.querySelector("span")?.textContent === "Movement"));
  } finally { await ui.cleanup(); }
});

test("Long option lists search locally, preserve selection and return focus", async () => {
  const calls: URL[] = [];
  const skills = ["Footwork", "Striking", "Grappling", "Defence", "Clinch work", "Angle exits", "Create angles", "Takedown defence", "Takedown entries", "Manage range", "Cut off the ring", "Ring positioning", "Cage positioning", "Set up counters", "Apply pressure", "Recover your base", "Scrambles & stand-ups", "Kicking & kick recovery", "Hand-foot timing", "Cue-response practice", "Stance transitions", "Decision practice"];
  const ui = await mount((async input => {
    calls.push(new URL(String(input), "http://localhost"));
    return json(response({ facets: { skill_focus: skills.map((label, i) => ({ value: `skill_${i}`, label, count: i + 1 })) } }));
  }) as typeof fetch);
  try {
    await ui.click("Filters");
    const open = async () => act(async () => document.querySelector<HTMLButtonElement>('button[aria-label^="Skill focus: "]')!.click());
    await open();
    assert.equal(document.querySelectorAll('[data-value]').length, 23);
    const search = document.querySelector<HTMLInputElement>('input[placeholder="Search options…"]')!;
    assert.equal(document.activeElement?.textContent, "← Back to filters");
    const before = calls.length;
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!.call(search, "takedown def");
      search.dispatchEvent(new window.Event("input", { bubbles: true }));
    });
    assert.equal(document.querySelectorAll('[data-value]').length, 2);
    assert.equal(calls.length, before);
    await act(async () => document.querySelector<HTMLButtonElement>('[data-value="skill_7"]')!.click()); await settle();
    assert.equal(calls.at(-1)?.searchParams.get("skill_focus"), "skill_7");
    assert.equal(document.activeElement?.getAttribute("aria-label"), "Skill focus: Takedown defence");
    await open();
    assert.equal(document.querySelector('[data-value="skill_7"]')?.getAttribute("aria-pressed"), "true");
    await act(async () => document.querySelector<HTMLButtonElement>('[data-value=""]')!.click()); await settle();
    assert.equal(calls.at(-1)?.searchParams.get("skill_focus"), null);
    const other = document.querySelector<HTMLDetailsElement>("details")!;
    await act(async () => { other.open = true; other.dispatchEvent(new window.Event("toggle")); });
    await act(async () => document.querySelector<HTMLButtonElement>('button[aria-label="Equipment: Any"]')!.click());
    await act(async () => document.querySelector<HTMLButtonElement>('[data-value=""]')!.click()); await settle();
    assert.equal(document.querySelector<HTMLDetailsElement>("details")?.open, true);
    assert.equal(document.activeElement?.getAttribute("aria-label"), "Equipment: Any");
  } finally { await ui.cleanup(); }
});
