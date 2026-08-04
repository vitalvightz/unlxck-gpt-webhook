import test from "node:test";
import assert from "node:assert/strict";

import "../test-dom";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import { GlobalFeedback } from "./global-feedback";

type Deferred<T> = {
  promise: Promise<T>;
  resolve: (value: T) => void;
};

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => {
    resolve = next;
  });
  return { promise, resolve };
}

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

function enterDescription(textarea: HTMLTextAreaElement, value: string) {
  const valueSetter = Object.getOwnPropertyDescriptor(
    window.HTMLTextAreaElement.prototype,
    "value",
  )?.set;
  assert.ok(valueSetter);
  valueSetter.call(textarea, value);
  textarea.dispatchEvent(new window.Event("input", { bubbles: true }));
}

test("global form accepts only one in-flight submission", async () => {
  const originalFetch = globalThis.fetch;
  const pendingPost = deferred<Response>();
  let postCalls = 0;
  globalThis.fetch = async (_input, init) => {
    if (init?.method === "POST") {
      postCalls += 1;
      return pendingPost.promise;
    }
    return jsonResponse(null);
  };
  const { container, root } = mount();

  try {
    await act(async () => {
      root.render(<GlobalFeedback token="test-token" />);
    });
    const description = container.querySelector<HTMLTextAreaElement>("#global-feedback-description");
    assert.ok(description);
    act(() => enterDescription(description, "Button clipped in Settings"));

    const form = container.querySelector("form");
    assert.ok(form);
    act(() => {
      form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
      form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
    });

    assert.equal(postCalls, 1);
    pendingPost.resolve(jsonResponse({
      id: "feedback-2",
      surface: "global",
      category: "bug_report",
      response: null,
      reason: null,
      comment: "Button clipped in Settings",
      priority: "normal",
      has_screenshot: false,
      created_at: "2026-07-12T00:00:00Z",
      updated_at: "2026-07-12T00:00:00Z",
    }, 201));
    await settle();
    assert.match(container.textContent ?? "", /Feedback sent\. Thank you\./);
  } finally {
    globalThis.fetch = originalFetch;
    cleanup(container, root);
  }
});
