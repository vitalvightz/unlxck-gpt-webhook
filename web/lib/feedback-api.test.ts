import test from "node:test";
import assert from "node:assert/strict";

import { submitGlobalFeedback } from "./api";

test("global feedback sends multipart without a forged JSON content type", async () => {
  const originalFetch = globalThis.fetch;
  let capturedInit: RequestInit | undefined;
  globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
    capturedInit = init;
    return new Response(
      JSON.stringify({
        id: "feedback-1",
        surface: "global",
        category: "bug_report",
        response: null,
        reason: null,
        comment: "",
        priority: "normal",
        has_screenshot: false,
        created_at: "",
        updated_at: "",
      }),
      { status: 201, headers: { "content-type": "application/json" } },
    );
  }) as typeof fetch;

  try {
    await submitGlobalFeedback("token", {
      category: "bug_report",
      description: "Clipped button",
      contact_allowed: true,
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.ok(capturedInit?.body instanceof FormData);
  const headers = new Headers(capturedInit?.headers);
  assert.equal(headers.get("content-type"), null);
  assert.equal(headers.get("authorization"), "Bearer token");
  const form = capturedInit?.body as FormData;
  assert.equal(form.get("category"), "bug_report");
  assert.equal(form.get("description"), "Clipped button");
  assert.equal(form.get("contact_allowed"), "true");
});
