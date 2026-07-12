import test from "node:test";
import assert from "node:assert/strict";

import "../test-dom";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import { ContextualFeedback, THUMB_PATHS } from "./contextual-feedback";

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

function savedYesFeedback() {
  return {
    id: "feedback-1",
    surface: "plan",
    category: "plan_usefulness",
    response: "yes",
    reason: null,
    comment: "",
    priority: "normal",
    has_screenshot: false,
    created_at: "2026-07-12T20:00:00Z",
    updated_at: "2026-07-12T20:00:00Z",
  };
}

test("load failure hides choices and Retry restores correctly oriented controls", async () => {
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return calls === 1
      ? jsonResponse({ detail: "feedback store unavailable" }, 503)
      : jsonResponse(null);
  };
  const { container, root } = mount();

  try {
    await act(async () => {
      root.render(<ContextualFeedback token="test-token" surface="daily_recommendation" />);
    });
    await settle();

    assert.match(container.textContent ?? "", /Feedback couldn’t load\./);
    assert.equal(container.querySelectorAll(".feedback-choice").length, 0);

    const retry = container.querySelector<HTMLButtonElement>(".feedback-load-failed button");
    assert.ok(retry);
    await act(async () => retry.click());
    await settle();

    assert.equal(calls, 2);
    assert.doesNotMatch(container.textContent ?? "", /Feedback couldn’t load\./);
    const choices = Array.from(container.querySelectorAll<HTMLButtonElement>(".feedback-choice"));
    assert.equal(choices.length, 3);
    assert.equal(choices[0]?.querySelector("path")?.getAttribute("d"), THUMB_PATHS.up);
    assert.equal(choices[1]?.querySelector("path")?.getAttribute("d"), THUMB_PATHS.down);
  } finally {
    globalThis.fetch = originalFetch;
    cleanup(container, root);
  }
});

test("submission failure keeps the feedback controls visible", async () => {
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return calls === 1
      ? jsonResponse(null)
      : jsonResponse({ detail: "Feedback could not be sent. Try again." }, 503);
  };
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

    assert.equal(calls, 2);
    assert.match(container.querySelector(".feedback-error")?.textContent ?? "", /Feedback could not be sent/);
    assert.ok(container.querySelector(".feedback-actions"));
  } finally {
    globalThis.fetch = originalFetch;
    cleanup(container, root);
  }
});

test("rapid Yes clicks create only one submission request", async () => {
  const originalFetch = globalThis.fetch;
  let calls = 0;
  let resolveSubmission: ((response: Response) => void) | undefined;
  globalThis.fetch = async () => {
    calls += 1;
    if (calls === 1) return jsonResponse(null);
    return await new Promise<Response>((resolve) => {
      resolveSubmission = resolve;
    });
  };
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

    await act(async () => {
      yes.click();
      yes.click();
      await Promise.resolve();
    });

    assert.equal(calls, 2);
    assert.ok(resolveSubmission);

    await act(async () => {
      resolveSubmission?.(jsonResponse(savedYesFeedback()));
      await Promise.resolve();
    });
    await settle();

    assert.match(container.textContent ?? "", /Feedback sent/);
  } finally {
    globalThis.fetch = originalFetch;
    cleanup(container, root);
  }
});
