import test from "node:test";
import assert from "node:assert/strict";

import "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";

import { PlanSwitchDialog } from "./plan-switch-dialog";

test("switch keeps the previous plan by default and archives only when selected", async () => {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const actions: string[] = [];
  try {
    act(() => root.render(<PlanSwitchDialog plan={{ fight_date: "2026-10-11" }} isPending={false} onConfirm={async (action) => { actions.push(action); }} onCancel={() => {}} />));
    const dialog = document.querySelector('[role="dialog"]')!;
    assert.match(dialog.textContent!, /Fight camp/);
    assert.match(dialog.textContent!, /Sun 11 Oct 2026/);
    assert.doesNotMatch(dialog.textContent!, /Pause current|Start after/);
    const checkbox = dialog.querySelector("input")!;
    const confirm = dialog.querySelector("button")!;
    assert.equal(checkbox.checked, false);
    await act(async () => confirm.click());
    act(() => checkbox.click());
    await act(async () => confirm.click());
    assert.deepEqual(actions, ["pause", "replace"]);
  } finally {
    act(() => root.unmount());
    container.remove();
  }
});

test("open plan shows no fight date, traps focus, cancels with Escape and restores focus", () => {
  const container = document.createElement("div");
  const trigger = document.createElement("button");
  document.body.append(trigger, container);
  trigger.focus();
  const root = createRoot(container);
  let cancels = 0;
  try {
    act(() => root.render(<PlanSwitchDialog plan={{ plan_name: "Off-season strength" }} isPending={false} onConfirm={async () => {}} onCancel={() => { cancels++; }} />));
    const dialog = document.querySelector('[role="dialog"]')!;
    assert.match(dialog.textContent!, /Off-season strength/);
    assert.match(dialog.textContent!, /No fight date/);
    assert.equal(document.activeElement, dialog);
    const checkbox = dialog.querySelector("input")!;
    const cancel = dialog.querySelectorAll("button")[1];
    cancel.focus();
    act(() => document.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true })));
    assert.equal(document.activeElement, checkbox);
    act(() => document.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true, cancelable: true })));
    assert.equal(document.activeElement, cancel);
    act(() => document.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
    assert.equal(cancels, 1);
    act(() => root.unmount());
    assert.equal(document.activeElement, trigger);
  } finally {
    act(() => root.unmount());
    container.remove();
    trigger.remove();
  }
});

test("pending switch blocks controls, backdrop and Escape; failures remain visible", () => {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  let cancels = 0;
  try {
    act(() => root.render(<PlanSwitchDialog plan={{}} isPending={true} onConfirm={async () => {}} onCancel={() => { cancels++; }} />));
    const dialog = document.querySelector('[role="dialog"]')!;
    assert.equal(dialog.getAttribute("aria-busy"), "true");
    assert.match(dialog.textContent!, /Switching/);
    for (const control of dialog.querySelectorAll<HTMLInputElement | HTMLButtonElement>("input, button")) assert.equal(control.disabled, true);
    act(() => {
      (dialog.parentElement as HTMLElement).click();
      document.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    assert.equal(cancels, 0);
    act(() => root.render(<PlanSwitchDialog plan={{}} isPending={false} errorMessage="Unable to switch plan" onConfirm={async () => {}} onCancel={() => { cancels++; }} />));
    assert.equal(document.querySelector('[role="alert"]')?.textContent, "Unable to switch plan");
    act(() => document.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
    assert.equal(cancels, 1);
  } finally {
    act(() => root.unmount());
    container.remove();
  }
});
