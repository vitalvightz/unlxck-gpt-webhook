import test from "node:test";
import assert from "node:assert/strict";

import { window as domWindow } from "../test-dom";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

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

function mount(): { container: HTMLElement; root: Root } {
  const container = document.createElement("div");
  document.body.appendChild(container);
  return { container, root: createRoot(container) };
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
function stubCheckin(options: { fail?: boolean } = {}) {
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
    return new Response(JSON.stringify({ open_injuries: [] }), {
      status: 201,
      headers: { "content-type": "application/json" },
    });
  }) as typeof globalThis.fetch;
  return { calls, restore: () => void (globalThis.fetch = originalFetch) };
}

test("marking a skin injury worse asks the surface follow-up before saving anything", async () => {
  const { calls, restore } = stubCheckin();
  const { container, root } = mount();

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

    act(() => root.unmount());
  } finally {
    restore();
  }
});

test("a failed worse update leaves the injury unselected and the follow-up open", async () => {
  const { calls, restore } = stubCheckin({ fail: true });
  const { container, root } = mount();

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

    act(() => root.unmount());
  } finally {
    restore();
  }
});

test("a non-surface injury marked worse saves directly, with no skin questions", async () => {
  const { calls, restore } = stubCheckin();
  const { container, root } = mount();

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

    act(() => root.unmount());
  } finally {
    restore();
  }
});

test("an ordinary status update never shows the skin questions", async () => {
  const { calls, restore } = stubCheckin();
  const { container, root } = mount();

  try {
    await act(async () => {
      root.render(
        <TodayInjuryManager openInjuries={[BLISTER]} token="t" onRefresh={async () => {}} />,
      );
    });

    await click(statusButton(container, "Same"));

    assert.deepEqual(calls, [{ injuries: [{ flag_id: "flag-blister", status: "ongoing" }] }]);
    assert.doesNotMatch(container.textContent ?? "", /Is it open or burst\?/);

    act(() => root.unmount());
  } finally {
    restore();
  }
});

test("clearing an injury is not marked selected until the confirmed write succeeds", async () => {
  const failing = stubCheckin({ fail: true });
  const { container, root } = mount();

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

    act(() => root.unmount());
  } finally {
    succeeding.restore();
  }
});

test("a restricted wound reported easing rechecks the skin before the restriction lifts", async () => {
  const { calls, restore } = stubCheckin();
  const { container, root } = mount();

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

    act(() => root.unmount());
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
  const { container, root } = mount();

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

    act(() => root.unmount());
  } finally {
    restore();
  }
});

test("a stable skin injury reported easing saves directly, with no recheck", async () => {
  const { calls, restore } = stubCheckin();
  const { container, root } = mount();

  try {
    await act(async () => {
      root.render(
        <TodayInjuryManager openInjuries={[BLISTER]} token="t" onRefresh={async () => {}} />,
      );
    });

    await click(statusButton(container, "Easing"));

    assert.deepEqual(calls, [{ injuries: [{ flag_id: "flag-blister", status: "improving" }] }]);
    assert.doesNotMatch(container.textContent ?? "", /Is the skin closed now\?/);

    act(() => root.unmount());
  } finally {
    restore();
  }
});
