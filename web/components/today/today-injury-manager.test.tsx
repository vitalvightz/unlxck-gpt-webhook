import test from "node:test";
import assert from "node:assert/strict";

import { window as domWindow } from "../test-dom";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import { ToastProvider } from "../toast-provider";

import { TodayInjuryManager } from "./today-injury-manager";
import type { InjuryFlagRecord } from "@/lib/types";

// jsdom has no matchMedia; the card's body-map select reads it on mount.
if (typeof domWindow.matchMedia !== "function") {
  Object.defineProperty(domWindow, "matchMedia", {
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

const BLISTER: InjuryFlagRecord = {
  id: "flag-blister",
  athlete_id: "athlete-1",
  source: "checkin",
  body_area: "left foot",
  description: "blister on left foot",
  label: "Left foot blister",
  severity: "moderate",
  status: "open",
  latest_reported_status: "ongoing",
  surface_class: "stable_surface",
  created_at: "2026-07-30T08:00:00Z",
  updated_at: "2026-07-30T08:00:00Z",
};

const OPEN_BLISTER: InjuryFlagRecord = {
  ...BLISTER,
  latest_reported_status: "worse",
  skin_integrity: "open",
  bleeding_status: "controlled",
  drainage: "none",
  infection_signs: [],
  coverable: "yes",
  friction_or_contact_problem: "yes",
  surface_class: "surface_no_contact",
};

const SHOULDER: InjuryFlagRecord = {
  ...BLISTER,
  id: "flag-shoulder",
  body_area: "left shoulder",
  description: "shoulder strain",
  label: "Left shoulder strain",
  surface_class: "non_surface",
};

function mount(): { container: HTMLElement; root: Root; cleanup: () => void } {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  // Unmounting tears down React's tree but leaves the host node parented to
  // document.body, so every test used to leave an orphan div behind for the
  // next one to query across. Cleanup detaches the node as well.
  return {
    container,
    root,
    cleanup: () => {
      act(() => root.unmount());
      container.remove();
    },
  };
}

async function settle() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

function buttonNamed(container: HTMLElement, label: string): HTMLButtonElement {
  const match = Array.from(container.querySelectorAll("button")).find(
    (button) => button.textContent?.trim() === label,
  );
  assert.ok(match, `expected a "${label}" button`);
  return match as HTMLButtonElement;
}

function statusButton(container: HTMLElement, label: string): HTMLButtonElement {
  const match = Array.from(container.querySelectorAll(".today-segment-row button")).find(
    (button) => button.textContent?.trim() === label,
  );
  assert.ok(match, `expected a "${label}" status button`);
  return match as HTMLButtonElement;
}

/** Selected styling means SAVED. A pending confirmation must never carry it. */
function assertNotSelected(button: HTMLButtonElement) {
  assert.equal(button.getAttribute("aria-pressed"), "false");
  assert.ok(
    !button.classList.contains("today-segment-active"),
    "expected no selected styling before the write is confirmed",
  );
}

function assertSelected(button: HTMLButtonElement) {
  assert.equal(button.getAttribute("aria-pressed"), "true");
  assert.ok(button.classList.contains("today-segment-active"));
  assert.ok(!button.classList.contains("today-segment-pending"));
}

async function click(element: HTMLElement) {
  await act(async () => {
    element.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  });
  await settle();
}

/** Stub /api/today/injury-checkin, capturing what was posted. */
function stubCheckin(options: { fail?: boolean; openInjuries?: InjuryFlagRecord[] } = {}) {
  const calls: Array<Record<string, unknown>> = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_input: unknown, init?: RequestInit) => {
    calls.push(JSON.parse(String(init?.body ?? "{}")));
    if (options.fail) {
      return new Response(JSON.stringify({ detail: "Injury update failed." }), {
        status: 500,
        headers: { "content-type": "application/json" },
      });
    }
    return new Response(JSON.stringify({ open_injuries: options.openInjuries ?? [] }), {
      status: 201,
      headers: { "content-type": "application/json" },
    });
  }) as typeof globalThis.fetch;
  return { calls, restore: () => void (globalThis.fetch = originalFetch) };
}

test("marking a skin injury worse asks the surface follow-up before saving anything", async () => {
  const { calls, restore } = stubCheckin();
  const { container, root, cleanup } = mount();

  try {
    await act(async () => {
      root.render(
        <TodayInjuryManager openInjuries={[BLISTER]} token="t" onRefresh={async () => {}} />,
      );
    });

    await click(statusButton(container, "Worse"));

    // Nothing is sent, and nothing reads as saved, until the follow-up is done.
    assert.equal(calls.length, 0);
    assertNotSelected(statusButton(container, "Worse"));
    assert.ok(statusButton(container, "Worse").classList.contains("today-segment-pending"));
    assert.match(container.textContent ?? "", /Is it open or burst\?/);
    assert.match(container.textContent ?? "", /Bleeding or weeping\?/);
    assert.match(container.textContent ?? "", /Any infection signs\?/);
    assert.match(container.textContent ?? "", /Can it stay covered\?/);
    assert.match(container.textContent ?? "", /Is rubbing or contact the problem\?/);

    await click(buttonNamed(container, "Open or burst"));
    await click(buttonNamed(container, "Pus"));
    await click(buttonNamed(container, "Save update"));

    assert.equal(calls.length, 1);
    assert.deepEqual(calls[0], {
      injuries: [
        {
          flag_id: "flag-blister",
          status: "worse",
          skin_integrity: "open",
          infection_signs: ["pus"],
          coverable: "unknown",
          friction_or_contact_problem: "unknown",
          bleeding_status: "none",
          drainage: "none",
        },
      ],
    });
    // Only now is it marked as saved, and the follow-up closes.
    assertSelected(statusButton(container, "Worse"));
    assert.doesNotMatch(container.textContent ?? "", /Is it open or burst\?/);

    cleanup();
  } finally {
    restore();
  }
});

test("a medically concerning worse answer reports the raised severity immediately", async () => {
  const severeWound: InjuryFlagRecord = {
    ...BLISTER,
    severity: "severe",
    latest_reported_status: "worse",
    skin_integrity: "open",
    drainage: "present",
    infection_signs: ["pus"],
    coverable: "no",
    surface_class: "surface_medical_review",
  };
  const { restore } = stubCheckin({ openInjuries: [severeWound] });
  const { container, root, cleanup } = mount();

  try {
    await act(async () => {
      root.render(
        <ToastProvider>
          <TodayInjuryManager openInjuries={[{ ...BLISTER, severity: "mild" }]} token="t" onRefresh={async () => {}} />
        </ToastProvider>,
      );
    });

    await click(statusButton(container, "Worse"));
    await click(buttonNamed(container, "Open or burst"));
    await click(buttonNamed(container, "Pus"));
    await click(buttonNamed(container, "Save update"));

    assert.match(container.textContent ?? "", /Severity raised to severe/);
    assert.match(container.textContent ?? "", /skin injury needs checking/i);

    cleanup();
  } finally {
    restore();
  }
});

test("a failed worse update leaves the injury unselected and the follow-up open", async () => {
  const { calls, restore } = stubCheckin({ fail: true });
  const { container, root, cleanup } = mount();

  try {
    await act(async () => {
      root.render(
        <TodayInjuryManager openInjuries={[BLISTER]} token="t" onRefresh={async () => {}} />,
      );
    });

    await click(statusButton(container, "Worse"));
    await click(buttonNamed(container, "Save update"));

    assert.equal(calls.length, 1);
    assertNotSelected(statusButton(container, "Worse"));
    // The answers are still on screen, so a retry does not start from scratch.
    assert.match(container.textContent ?? "", /Is it open or burst\?/);

    cleanup();
  } finally {
    restore();
  }
});

test("a non-surface injury marked worse saves directly, with no skin questions", async () => {
  const { calls, restore } = stubCheckin();
  const { container, root, cleanup } = mount();

  try {
    await act(async () => {
      root.render(
        <TodayInjuryManager openInjuries={[SHOULDER]} token="t" onRefresh={async () => {}} />,
      );
    });

    await click(statusButton(container, "Worse"));

    assert.deepEqual(calls, [{ injuries: [{ flag_id: "flag-shoulder", status: "worse" }] }]);
    assert.doesNotMatch(container.textContent ?? "", /Is it open or burst\?/);
    assertSelected(statusButton(container, "Worse"));

    cleanup();
  } finally {
    restore();
  }
});

test("an ordinary status update never shows the skin questions", async () => {
  const { calls, restore } = stubCheckin();
  const { container, root, cleanup } = mount();

  try {
    await act(async () => {
      root.render(
        <TodayInjuryManager openInjuries={[BLISTER]} token="t" onRefresh={async () => {}} />,
      );
    });

    await click(statusButton(container, "Same"));

    assert.deepEqual(calls, [{ injuries: [{ flag_id: "flag-blister", status: "ongoing" }] }]);
    assert.doesNotMatch(container.textContent ?? "", /Is it open or burst\?/);

    cleanup();
  } finally {
    restore();
  }
});

test("clearing an injury is not marked selected until the confirmed write succeeds", async () => {
  const failing = stubCheckin({ fail: true });
  const { container, root, cleanup } = mount();

  try {
    await act(async () => {
      root.render(
        <TodayInjuryManager openInjuries={[BLISTER]} token="t" onRefresh={async () => {}} />,
      );
    });

    await click(statusButton(container, "Cleared"));
    // The confirmation is open, but nothing has been sent or marked saved.
    assert.equal(failing.calls.length, 0);
    assertNotSelected(statusButton(container, "Cleared"));
    assert.ok(statusButton(container, "Cleared").classList.contains("today-segment-pending"));

    await click(buttonNamed(container, "Yes, clear"));

    // The write failed: no selected state, and the confirmation stays open.
    assert.equal(failing.calls.length, 1);
    assertNotSelected(statusButton(container, "Cleared"));
    assert.match(container.textContent ?? "", /Clear this injury\?/);
  } finally {
    failing.restore();
  }

  const succeeding = stubCheckin();
  try {
    await click(buttonNamed(container, "Yes, clear"));

    assert.equal(succeeding.calls.length, 1);
    assertSelected(statusButton(container, "Cleared"));
    assert.doesNotMatch(container.textContent ?? "", /Clear this injury\?/);

    cleanup();
  } finally {
    succeeding.restore();
  }
});

test("a restricted wound reported easing rechecks the skin before the restriction lifts", async () => {
  const { calls, restore } = stubCheckin();
  const { container, root, cleanup } = mount();

  try {
    await act(async () => {
      root.render(
        <TodayInjuryManager openInjuries={[OPEN_BLISTER]} token="t" onRefresh={async () => {}} />,
      );
    });

    await click(statusButton(container, "Easing"));

    // Nothing is written on the tap alone: an open wound cannot stop blocking
    // contact without the athlete saying the skin has closed.
    assert.equal(calls.length, 0);
    assertNotSelected(statusButton(container, "Easing"));
    assert.match(container.textContent ?? "", /Is the skin closed now\?/);
    // The recheck is the short set — the routing question is not re-asked.
    assert.doesNotMatch(container.textContent ?? "", /Is rubbing or contact the problem\?/);

    await click(buttonNamed(container, "Still closed"));
    await click(buttonNamed(container, "No"));
    await click(buttonNamed(container, "Save update"));

    assert.deepEqual(calls, [
      {
        injuries: [
          {
            flag_id: "flag-blister",
            status: "improving",
            skin_integrity: "intact",
            infection_signs: [],
            // Unasked in a recheck, so friction is not sent and keeps its
            // stored value; coverable comes back as recorded.
            coverable: "yes",
            bleeding_status: "none",
            drainage: "none",
          },
        ],
      },
    ]);
    assertSelected(statusButton(container, "Easing"));

    cleanup();
  } finally {
    restore();
  }
});

test("the recheck opens on what is stored, so saving it cannot silently clear an answer", async () => {
  const { calls, restore } = stubCheckin();
  const infected: InjuryFlagRecord = {
    ...OPEN_BLISTER,
    infection_signs: ["pus"],
    surface_class: "surface_medical_review",
  };
  const { container, root, cleanup } = mount();

  try {
    await act(async () => {
      root.render(
        <TodayInjuryManager openInjuries={[infected]} token="t" onRefresh={async () => {}} />,
      );
    });

    await click(statusButton(container, "Same"));
    // Pre-filled from the record: the stored infection sign is still selected.
    assert.equal(buttonNamed(container, "Pus").getAttribute("aria-pressed"), "true");
    assert.equal(buttonNamed(container, "Open or burst").getAttribute("aria-pressed"), "true");

    await click(buttonNamed(container, "Save update"));

    const sent = (calls[0].injuries as Array<Record<string, unknown>>)[0];
    assert.equal(sent.status, "ongoing");
    // Untouched answers survive the recheck rather than being blanked by it.
    assert.deepEqual(sent.infection_signs, ["pus"]);
    assert.equal(sent.skin_integrity, "open");
    assert.equal(sent.bleeding_status, "controlled");

    cleanup();
  } finally {
    restore();
  }
});

test("a stable skin injury reported easing saves directly, with no recheck", async () => {
  const { calls, restore } = stubCheckin();
  const { container, root, cleanup } = mount();

  try {
    await act(async () => {
      root.render(
        <TodayInjuryManager openInjuries={[BLISTER]} token="t" onRefresh={async () => {}} />,
      );
    });

    await click(statusButton(container, "Easing"));

    assert.deepEqual(calls, [{ injuries: [{ flag_id: "flag-blister", status: "improving" }] }]);
    assert.doesNotMatch(container.textContent ?? "", /Is the skin closed now\?/);

    cleanup();
  } finally {
    restore();
  }
});

// A wound that is bleeding uncontrollably AND draining. The follow-up asks one
// bleeding question, and "Won't stop" is the answer it prefills — which says
// nothing about drainage.
const LEAKING_UNCONTROLLED_BLISTER: InjuryFlagRecord = {
  ...OPEN_BLISTER,
  bleeding_status: "uncontrolled",
  drainage: "present",
  surface_class: "surface_medical_review",
};

test("an untouched recheck preserves a stored drainage the bleeding answer does not cover", async () => {
  // Saving the canonical mapping for "Won't stop" wrote drainage: "unknown"
  // over a recorded "present" — losing a safety signal the athlete never
  // touched, on a recheck of a wound already flagged for medical review.
  const { calls, restore } = stubCheckin();
  const { container, root, cleanup } = mount();

  try {
    await act(async () => {
      root.render(
        <TodayInjuryManager
          openInjuries={[LEAKING_UNCONTROLLED_BLISTER]}
          token="t"
          onRefresh={async () => {}}
        />,
      );
    });

    await click(statusButton(container, "Easing"));
    await click(buttonNamed(container, "Save update"));

    const sent = (calls[0]?.injuries as Array<Record<string, unknown>>)[0];
    assert.equal(sent.bleeding_status, "uncontrolled");
    assert.equal(sent.drainage, "present");
    assert.notEqual(sent.drainage, "unknown");

    cleanup();
  } finally {
    restore();
  }
});

test("changing the bleeding answer does replace the stored drainage", async () => {
  // The preservation above must not freeze the field: an answered question
  // still overwrites what was on record.
  const { calls, restore } = stubCheckin();
  const { container, root, cleanup } = mount();

  try {
    await act(async () => {
      root.render(
        <TodayInjuryManager
          openInjuries={[LEAKING_UNCONTROLLED_BLISTER]}
          token="t"
          onRefresh={async () => {}}
        />,
      );
    });

    await click(statusButton(container, "Easing"));
    await click(buttonNamed(container, "No"));
    await click(buttonNamed(container, "Save update"));

    const sent = (calls[0]?.injuries as Array<Record<string, unknown>>)[0];
    assert.equal(sent.bleeding_status, "none");
    assert.equal(sent.drainage, "none");

    cleanup();
  } finally {
    restore();
  }
});

test("a write in flight locks every row, so another injury's follow-up cannot be discarded", async () => {
  // The other row stayed clickable, the handler closed the open follow-up, and
  // updateInjury then refused the request because a write was pending — so the
  // answers being filled in were lost on the way to a no-op.
  let release: (() => void) | null = null;
  const originalFetch = globalThis.fetch;
  const calls: Array<Record<string, unknown>> = [];
  globalThis.fetch = (async (_input: unknown, init?: RequestInit) => {
    calls.push(JSON.parse(String(init?.body ?? "{}")));
    await new Promise<void>((resolve) => {
      release = resolve;
    });
    return new Response(JSON.stringify({ open_injuries: [] }), {
      status: 201,
      headers: { "content-type": "application/json" },
    });
  }) as typeof globalThis.fetch;

  const { container, root, cleanup } = mount();

  try {
    await act(async () => {
      root.render(
        <TodayInjuryManager
          openInjuries={[SHOULDER, OPEN_BLISTER]}
          token="t"
          onRefresh={async () => {}}
        />,
      );
    });

    // Start a write on the shoulder and leave it hanging.
    await click(statusButton(container, "Easing"));
    assert.equal(calls.length, 1);

    // Every status button is now disabled, including the other injury's.
    // Scoped to the tracked-injury rows: the "add an injury" form below has its
    // own segment row, and that flow is not what the pending write blocks.
    const allStatusButtons = Array.from(
      container.querySelectorAll<HTMLButtonElement>(".today-injury-item .today-segment-row button"),
    );
    assert.ok(
      allStatusButtons.every((button) => button.disabled),
      "expected every row's status actions to be locked while a write is in flight",
    );

    // And a click that slips through (a stale pointer event) changes nothing.
    await click(allStatusButtons[allStatusButtons.length - 1]);
    assert.equal(calls.length, 1);

    await act(async () => {
      release?.();
      await Promise.resolve();
    });
    await settle();

    cleanup();
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("a pending answer is announced, not just outlined", async () => {
  // aria-pressed stays false until the write is confirmed, so the "captured but
  // not saved" state needs its own accessible description.
  const { restore } = stubCheckin();
  const { container, root, cleanup } = mount();

  try {
    await act(async () => {
      root.render(
        <TodayInjuryManager openInjuries={[BLISTER]} token="t" onRefresh={async () => {}} />,
      );
    });

    await click(statusButton(container, "Cleared"));

    const cleared = statusButton(container, "Cleared");
    assertNotSelected(cleared);
    const describedBy = cleared.getAttribute("aria-describedby");
    assert.ok(describedBy, "expected the pending button to describe its state");
    const hint = container.querySelector(`[id="${describedBy}"]`);
    assert.ok(hint, "expected the described element to exist");
    assert.match(hint?.textContent ?? "", /Not saved yet/);

    cleanup();
  } finally {
    restore();
  }
});

function mainInjury(overrides: Partial<InjuryFlagRecord> = {}): InjuryFlagRecord {
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

function mountMain(
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

function unmountMain(container: HTMLElement, root: Root) {
  act(() => root.unmount());
  container.remove();
}

function button(container: HTMLElement, label: string): HTMLButtonElement {
  const found = Array.from(container.querySelectorAll("button")).find(
    (item) => item.textContent?.trim() === label,
  );
  assert.ok(found, `Expected button labelled ${label}`);
  return found;
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
  const { container, root } = mountMain();
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
    unmountMain(container, root);
  }
});

test("active injuries stay first with name, type, severity, actions, and the add-another label", async () => {
  const { container, root } = mountMain([mainInjury()]);
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
    unmountMain(container, root);
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
  const { container, root } = mountMain([], async () => {
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
    unmountMain(container, root);
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
  const { container, root } = mountMain([], async () => {
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
    unmountMain(container, root);
  }
});

test("existing injury status actions still submit through the current refresh flow", async () => {
  const originalFetch = globalThis.fetch;
  let payload: unknown;
  let refreshes = 0;
  globalThis.fetch = async (_input, init) => {
    payload = JSON.parse(String(init?.body));
    return new Response(JSON.stringify({ open_injuries: [mainInjury()] }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };
  const { container, root } = mountMain([mainInjury()], async () => {
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
    unmountMain(container, root);
  }
});
