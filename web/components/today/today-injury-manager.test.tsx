import test from "node:test";
import assert from "node:assert/strict";

import "../test-dom";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import { ToastProvider } from "../toast-provider";
import type { InjuryFlagRecord } from "../../lib/types";
import { TodayInjuryManager } from "./today-injury-manager";

function injury(overrides: Partial<InjuryFlagRecord> = {}): InjuryFlagRecord {
  return {
    id: "injury-1",
    athlete_id: "athlete-1",
    plan_id: "plan-1",
    source: "manual",
    body_area: "Left shoulder",
    description: "Bruise",
    label: "Left shoulder",
    severity: "moderate",
    status: "open",
    created_at: "2026-07-30T08:00:00Z",
    updated_at: "2026-07-30T08:00:00Z",
    ...overrides,
  };
}

function mount(
  openInjuries: InjuryFlagRecord[] = [],
  onRefresh: () => Promise<void> = async () => {},
): { container: HTMLElement; root: Root } {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <ToastProvider>
        <TodayInjuryManager openInjuries={openInjuries} token="token" onRefresh={onRefresh} />
      </ToastProvider>,
    );
  });
  return { container, root };
}

function unmount(container: HTMLElement, root: Root) {
  act(() => root.unmount());
  container.remove();
}

async function settle() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

function button(container: HTMLElement, label: string): HTMLButtonElement {
  const found = Array.from(container.querySelectorAll("button")).find(
    (item) => item.textContent?.trim() === label,
  );
  assert.ok(found, `Expected button labelled ${label}`);
  return found;
}

async function click(target: HTMLElement) {
  await act(async () => target.click());
}

async function setInput(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
  assert.ok(setter);
  await act(async () => {
    setter.call(input, value);
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
}

test("add injury form is collapsed by default and opens from the empty-state trigger", async () => {
  const { container, root } = mount();
  try {
    const trigger = button(container, "+ Add injury");
    const form = container.querySelector<HTMLFormElement>("form.today-injury-add");
    assert.ok(form);
    assert.equal(trigger.getAttribute("aria-expanded"), "false");
    assert.equal(form.hidden, true);
    assert.match(container.textContent ?? "", /No injuries are being tracked/);

    await click(trigger);

    assert.equal(trigger.getAttribute("aria-expanded"), "true");
    assert.equal(trigger.textContent?.trim(), "Add injury");
    assert.equal(form.hidden, false);
    assert.equal(trigger.getAttribute("aria-controls"), form.id);
  } finally {
    unmount(container, root);
  }
});

test("active injuries stay first with name, type, severity, actions, and the add-another label", async () => {
  const { container, root } = mount([injury()]);
  try {
    const list = container.querySelector(".today-injury-list");
    const trigger = button(container, "+ Add another injury");
    assert.ok(list);
    assert.ok(
      Boolean(list.compareDocumentPosition(trigger) & window.Node.DOCUMENT_POSITION_FOLLOWING),
      "active injury list should appear before the add trigger",
    );
    assert.match(list.textContent ?? "", /Left shoulder/);
    assert.match(list.textContent ?? "", /Bruise/);
    assert.match(list.textContent ?? "", /moderate/);
    assert.ok(button(container, "Easing"));
    assert.ok(button(container, "Cleared"));
  } finally {
    unmount(container, root);
  }
});

test("successful injury submission refreshes, resets, and collapses the form", async () => {
  const originalFetch = globalThis.fetch;
  const requests: Array<{ url: string; body: unknown }> = [];
  let refreshes = 0;
  globalThis.fetch = async (input, init) => {
    requests.push({ url: String(input), body: JSON.parse(String(init?.body)) });
    return new Response(JSON.stringify({ open_injuries: [] }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };
  const { container, root } = mount([], async () => {
    refreshes += 1;
  });
  try {
    await click(button(container, "+ Add injury"));
    const area = container.querySelector<HTMLInputElement>("#today-injury-area");
    assert.ok(area);
    await setInput(area, "Left ankle");
    await click(button(container, "Soreness"));

    const form = container.querySelector<HTMLFormElement>("form.today-injury-add");
    assert.ok(form);
    await act(async () => {
      form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
    });
    await settle();

    assert.equal(refreshes, 1);
    assert.equal(requests.length, 1);
    assert.equal(requests[0]?.url, "/api/today/injury-checkin");
    assert.deepEqual(requests[0]?.body, {
      injuries: [
        {
          body_area: "Left ankle",
          description: "soreness",
          severity: "moderate",
          status: "ongoing",
        },
      ],
    });
    assert.equal(container.querySelector<HTMLFormElement>("form.today-injury-add")?.hidden, true);
    assert.equal(button(container, "+ Add injury").getAttribute("aria-expanded"), "false");

    await click(button(container, "+ Add injury"));
    assert.equal(container.querySelector<HTMLInputElement>("#today-injury-area")?.value, "");
    assert.equal(button(container, "Moderate").getAttribute("aria-pressed"), "true");
    assert.equal(button(container, "Soreness").getAttribute("aria-pressed"), "false");
  } finally {
    globalThis.fetch = originalFetch;
    unmount(container, root);
  }
});

test("failed injury submission leaves the populated form open", async () => {
  const originalFetch = globalThis.fetch;
  let refreshes = 0;
  globalThis.fetch = async () =>
    new Response(JSON.stringify({ detail: "Could not save injury" }), {
      status: 500,
      headers: { "content-type": "application/json" },
    });
  const { container, root } = mount([], async () => {
    refreshes += 1;
  });
  try {
    await click(button(container, "+ Add injury"));
    const area = container.querySelector<HTMLInputElement>("#today-injury-area");
    assert.ok(area);
    await setInput(area, "Right knee");
    await click(button(container, "Tightness"));
    const form = container.querySelector<HTMLFormElement>("form.today-injury-add");
    assert.ok(form);
    await act(async () => {
      form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
    });
    await settle();

    assert.equal(refreshes, 0);
    assert.equal(button(container, "Add injury").getAttribute("aria-expanded"), "true");
    assert.equal(container.querySelector<HTMLInputElement>("#today-injury-area")?.value, "Right knee");
    assert.match(document.body.textContent ?? "", /Could not save injury/);
  } finally {
    globalThis.fetch = originalFetch;
    unmount(container, root);
  }
});

test("existing injury status actions still submit through the current refresh flow", async () => {
  const originalFetch = globalThis.fetch;
  let payload: unknown;
  let refreshes = 0;
  globalThis.fetch = async (_input, init) => {
    payload = JSON.parse(String(init?.body));
    return new Response(JSON.stringify({ open_injuries: [injury()] }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };
  const { container, root } = mount([injury()], async () => {
    refreshes += 1;
  });
  try {
    await click(button(container, "Easing"));
    await settle();

    assert.deepEqual(payload, { injuries: [{ flag_id: "injury-1", status: "improving" }] });
    assert.equal(refreshes, 1);
    assert.equal(button(container, "Easing").getAttribute("aria-pressed"), "true");

    await click(button(container, "Cleared"));
    assert.match(container.textContent ?? "", /Clear this injury/);
    await click(button(container, "Cancel"));
    assert.doesNotMatch(container.textContent ?? "", /Clear this injury/);
  } finally {
    globalThis.fetch = originalFetch;
    unmount(container, root);
  }
});
