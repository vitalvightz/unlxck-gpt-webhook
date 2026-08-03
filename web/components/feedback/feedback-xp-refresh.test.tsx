import test from "node:test";
import assert from "node:assert/strict";

import "../test-dom";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import { ContextualFeedback } from "./contextual-feedback";
import { GlobalFeedback } from "./global-feedback";
import { XP_REFRESH_EVENT } from "@/lib/xp-events";

function mount(): { container: HTMLElement; root: Root } {
  const container = document.createElement("div");
  document.body.appendChild(container);
  return { container, root: createRoot(container) };
}

function cleanup(container: HTMLElement, root: Root) {
  act(() => root.unmount());
  container.remove();
}

async function settle() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function savedFeedback(surface: "plan" | "global") {
  return {
    id: `feedback-${surface}`,
    surface,
    category: surface === "plan" ? "plan_usefulness" : "bug_report",
    response: surface === "plan" ? "yes" : null,
    reason: null,
    comment: "",
    priority: "normal",
    has_screenshot: false,
    created_at: "2026-08-04T00:00:00Z",
    updated_at: "2026-08-04T00:00:00Z",
  };
}

test("contextual feedback requests an immediate XP refresh after a successful save", async () => {
  const originalFetch = globalThis.fetch;
  let refreshEvents = 0;
  const onRefresh = () => {
    refreshEvents += 1;
  };
  window.addEventListener(XP_REFRESH_EVENT, onRefresh);
  globalThis.fetch = async (_input, init) =>
    (init?.method ?? "GET") === "PUT"
      ? jsonResponse(savedFeedback("plan"))
      : jsonResponse(null);
  const { container, root } = mount();

  try {
    await act(async () => {
      root.render(<ContextualFeedback token="test-token" surface="plan" planId="plan-1" />);
    });
    await settle();

    const yes = Array.from(container.querySelectorAll<HTMLButtonElement>(".feedback-choice")).find(
      (button) => button.textContent?.includes("Yes"),
    );
    assert.ok(yes);
    await act(async () => yes.click());
    await settle();

    assert.equal(refreshEvents, 1);
  } finally {
    globalThis.fetch = originalFetch;
    window.removeEventListener(XP_REFRESH_EVENT, onRefresh);
    cleanup(container, root);
  }
});

test("global feedback requests an immediate XP refresh after a successful save", async () => {
  const originalFetch = globalThis.fetch;
  let refreshEvents = 0;
  const onRefresh = () => {
    refreshEvents += 1;
  };
  window.addEventListener(XP_REFRESH_EVENT, onRefresh);
  globalThis.fetch = async () => jsonResponse(savedFeedback("global"), 201);
  const { container, root } = mount();

  try {
    await act(async () => {
      root.render(<GlobalFeedback token="test-token" />);
    });

    const form = container.querySelector<HTMLFormElement>("form");
    assert.ok(form);
    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    await settle();

    assert.equal(refreshEvents, 1);
  } finally {
    globalThis.fetch = originalFetch;
    window.removeEventListener(XP_REFRESH_EVENT, onRefresh);
    cleanup(container, root);
  }
});
