import assert from "node:assert/strict";
import test from "node:test";
import { window } from "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";
import { ToastProvider } from "./toast-provider";
import { CustomPlanBuilder } from "./custom-plan-builder";

test("Token refresh keeps an opened plan and unsaved edits", async () => {
  const originalFetch = globalThis.fetch;
  const calls: string[] = [];
  const id = "00000000-0000-4000-8000-000000000099";
  globalThis.fetch = (async (input) => {
    calls.push(String(input));
    return new Response(
      JSON.stringify({
        id,
        name: "Demo Plan",
        kind: "self_directed",
        sessions: [],
        incomplete: true,
        created_at: "2026-10-11T12:00:00Z",
        updated_at: "2026-10-11T12:00:00Z",
      }),
    );
  }) as typeof fetch;
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const router = {
    push() {},
    replace() {},
    refresh() {},
    back() {},
    forward() {},
    prefetch() {},
    bfcacheId: "fixture",
  };
  const render = (token: string) => (
    <AppRouterContext.Provider value={router}>
      <ToastProvider>
        <CustomPlanBuilder planId={id} accessToken={token} />
      </ToastProvider>
    </AppRouterContext.Provider>
  );
  try {
    await act(async () => root.render(render("first-token")));
    const input = host.querySelector<HTMLInputElement>("input")!;
    assert.equal(input.value, "Demo Plan");
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!.call(input, "My edited plan");
      input.dispatchEvent(new window.Event("input", { bubbles: true }));
    });
    await act(async () => root.render(render("refreshed-token")));
    assert.equal(input.value, "My edited plan");
    assert.match(host.textContent!, /Unsaved changes/);
    assert.equal(calls.length, 1);
  } finally {
    await act(async () => root.unmount());
    host.remove();
    globalThis.fetch = originalFetch;
  }
});

test("rest days offer a pencil control that opens a new session", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const router = { push() {}, replace() {}, refresh() {}, back() {}, forward() {}, prefetch() {}, bfcacheId: "fixture" };
  try {
    await act(async () => root.render(
      <AppRouterContext.Provider value={router}>
        <ToastProvider><CustomPlanBuilder accessToken="test-token" /></ToastProvider>
      </AppRouterContext.Provider>,
    ));
    assert.match(host.textContent!, /Keep this day for recovery\./);
    const addSession = host.querySelector<HTMLButtonElement>('[aria-label="Add session on Monday"]')!;
    await act(async () => addSession.click());
    assert.equal(document.querySelector<HTMLInputElement>('input[value="Training"]')?.value, "Training");
    assert.match(document.body.textContent!, /New session/);
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});

test("a new session only joins the plan once confirmed, and the bin removes it", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const router = { push() {}, replace() {}, refresh() {}, back() {}, forward() {}, prefetch() {}, bfcacheId: "fixture" };
  const confirm = window.confirm;
  window.confirm = () => true;
  const sheetButton = (label: string) => [...document.querySelectorAll<HTMLButtonElement>(".injury-sheet button")].find(b => b.textContent?.trim() === label);
  try {
    await act(async () => root.render(
      <AppRouterContext.Provider value={router}>
        <ToastProvider><CustomPlanBuilder accessToken="test-token" /></ToastProvider>
      </AppRouterContext.Provider>,
    ));
    assert.doesNotMatch(host.textContent!, /Unassigned|No day set/);
    await act(async () => host.querySelector<HTMLButtonElement>('[aria-label="Add session on Monday"]')!.click());
    await act(async () => document.querySelector<HTMLButtonElement>('[aria-label="Close"], .injury-sheet-close')?.click());
    assert.match(host.textContent!, /Rest day/, "closing a new session's sheet adds nothing");

    await act(async () => host.querySelector<HTMLButtonElement>('[aria-label="Add session on Monday"]')!.click());
    await act(async () => sheetButton("Add session")!.closest("form")!.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true })));
    assert.equal(host.querySelectorAll('[aria-label^="Session "]').length, 1);
    assert.doesNotMatch(host.textContent!, /Unassigned|No day set/);
    assert.ok(host.querySelector('[aria-label="Add another session on Monday"]'));

    await act(async () => host.querySelector<HTMLButtonElement>('[aria-label="Remove Training"]')!.click());
    assert.equal(host.querySelectorAll('[aria-label^="Session "]').length, 0);
    assert.match(host.textContent!, /Rest day/);
  } finally {
    window.confirm = confirm;
    await act(async () => root.unmount());
    host.remove();
  }
});
