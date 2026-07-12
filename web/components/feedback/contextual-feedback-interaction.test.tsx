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

function savedNoFeedback() {
  return {
    ...savedYesFeedback(),
    response: "no",
    reason: "too_hard",
    comment: "Reduce the volume",
  };
}

test("controls render immediately and one Yes click submits when hydration fails", async () => {
  const originalFetch = globalThis.fetch;
  let getCalls = 0;
  let putCalls = 0;
  globalThis.fetch = async (_input, init) => {
    if ((init?.method ?? "GET") === "PUT") {
      putCalls += 1;
      return jsonResponse(savedYesFeedback());
    }
    getCalls += 1;
    return jsonResponse({ detail: "feedback store unavailable" }, 503);
  };
  const { container, root } = mount();

  try {
    await act(async () => {
      root.render(<ContextualFeedback token="test-token" surface="daily_recommendation" />);
    });

    const choices = Array.from(container.querySelectorAll<HTMLButtonElement>(".feedback-choice"));
    assert.equal(choices.length, 3);
    assert.equal(choices[0]?.querySelector("path")?.getAttribute("d"), THUMB_PATHS.up);
    assert.equal(choices[1]?.querySelector("path")?.getAttribute("d"), THUMB_PATHS.down);
    assert.doesNotMatch(container.textContent ?? "", /Loading feedback|Feedback couldn’t load|Retry/);
    assert.equal(getCalls, 1);
    assert.equal(putCalls, 0);

    await act(async () => choices[0]?.click());
    await settle();

    assert.equal(getCalls, 1);
    assert.equal(putCalls, 1);
    assert.match(container.textContent ?? "", /Feedback sent/);
  } finally {
    globalThis.fetch = originalFetch;
    cleanup(container, root);
  }
});

test("saved negative feedback hydrates after refresh without hiding controls first", async () => {
  const originalFetch = globalThis.fetch;
  let resolveHydration: ((response: Response) => void) | undefined;
  globalThis.fetch = async () => await new Promise<Response>((resolve) => {
    resolveHydration = resolve;
  });
  const { container, root } = mount();

  try {
    await act(async () => {
      root.render(<ContextualFeedback token="test-token" surface="plan" planId="plan-1" />);
    });
    assert.ok(container.querySelector(".feedback-actions"));
    assert.ok(resolveHydration);
    await act(async () => {
      resolveHydration?.(jsonResponse(savedNoFeedback()));
      await Promise.resolve();
    });
    await settle();

    assert.match(container.textContent ?? "", /Feedback sent/);
    const change = container.querySelector<HTMLButtonElement>(".feedback-sent-row button");
    assert.ok(change);
    await act(async () => change.click());

    const selected = container.querySelector<HTMLButtonElement>('.feedback-choice[aria-pressed="true"]');
    assert.match(selected?.textContent ?? "", /Needs improvement/);
    assert.equal(container.querySelector<HTMLTextAreaElement>("textarea")?.value, "Reduce the volume");
    assert.equal(container.querySelector<HTMLButtonElement>('[aria-pressed="true"].feedback-chip')?.textContent, "Too hard");
  } finally {
    globalThis.fetch = originalFetch;
    cleanup(container, root);
  }
});

test("a slow hydration response cannot overwrite a new user selection", async () => {
  const originalFetch = globalThis.fetch;
  let resolveHydration: ((response: Response) => void) | undefined;
  globalThis.fetch = async () => await new Promise<Response>((resolve) => {
    resolveHydration = resolve;
  });
  const { container, root } = mount();

  try {
    await act(async () => {
      root.render(<ContextualFeedback token="test-token" surface="plan" planId="plan-1" />);
    });
    const no = Array.from(container.querySelectorAll<HTMLButtonElement>(".feedback-choice")).find(
      (button) => button.textContent?.includes("Needs improvement"),
    );
    assert.ok(no);
    await act(async () => no.click());
    assert.ok(resolveHydration);

    await act(async () => {
      resolveHydration?.(jsonResponse(savedYesFeedback()));
      await Promise.resolve();
    });
    await settle();

    assert.equal(no.getAttribute("aria-pressed"), "true");
    assert.ok(container.querySelector(".feedback-comment"));
    assert.doesNotMatch(container.textContent ?? "", /Feedback sent/);
  } finally {
    globalThis.fetch = originalFetch;
    cleanup(container, root);
  }
});

test("submission failure keeps the feedback controls visible", async () => {
  const originalFetch = globalThis.fetch;
  let putCalls = 0;
  globalThis.fetch = async (_input, init) => {
    if ((init?.method ?? "GET") === "PUT") {
      putCalls += 1;
      return jsonResponse({ detail: "Feedback could not be sent. Try again." }, 503);
    }
    return jsonResponse(null);
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

    assert.equal(putCalls, 1);
    assert.match(container.querySelector(".feedback-error")?.textContent ?? "", /Feedback could not be sent/);
    assert.ok(container.querySelector(".feedback-actions"));
  } finally {
    globalThis.fetch = originalFetch;
    cleanup(container, root);
  }
});

test("rapid Yes clicks create only one submission request", async () => {
  const originalFetch = globalThis.fetch;
  let putCalls = 0;
  let resolveSubmission: ((response: Response) => void) | undefined;
  globalThis.fetch = async (_input, init) => {
    if ((init?.method ?? "GET") !== "PUT") return jsonResponse(null);
    putCalls += 1;
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

    assert.equal(putCalls, 1);
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
