import test from "node:test";
import assert from "node:assert/strict";

import "./test-dom";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import { AdminFeedbackPanel } from "./admin-feedback-panel";

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

test("admin feedback panel renders operator context without duplicating submitter email", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify([
    {
      id: "feedback-1",
      submitted_by_profile_id: "profile-1",
      submitter_email: "athlete@example.com",
      submitter_name: "",
      surface: "global",
      category: "safety_issue",
      response: null,
      reason: null,
      comment: "Unsafe loading",
      contact_allowed: true,
      priority: "safety",
      plan_id: null,
      today_checkin_id: null,
      camp_phase: "TAPER",
      app_version: "test-sha",
      has_screenshot: true,
      screenshot_expires_at: "2026-10-10T00:00:00Z",
      created_at: "2026-07-12T20:00:00Z",
      updated_at: "2026-07-12T20:00:00Z",
    },
  ]), { status: 200, headers: { "content-type": "application/json" } });
  const { container, root } = mount();

  try {
    await act(async () => {
      root.render(<AdminFeedbackPanel token="admin-token" reloadKey={0} />);
    });
    await settle();

    assert.match(container.textContent ?? "", /Latest feedback/);
    assert.match(container.textContent ?? "", /Safety issue/);
    assert.match(container.textContent ?? "", /Authenticated user/);
    assert.equal((container.textContent ?? "").match(/athlete@example\.com/g)?.length, 1);
    assert.match(container.textContent ?? "", /Contact permitted/);
    assert.match(container.textContent ?? "", /View private screenshot/);
    assert.match(container.textContent ?? "", /Email alerts are best-effort/);
  } finally {
    globalThis.fetch = originalFetch;
    act(() => root.unmount());
    container.remove();
  }
});

test("admin feedback panel obtains a short-lived screenshot link on demand", async () => {
  const originalFetch = globalThis.fetch;
  const requests: string[] = [];
  globalThis.fetch = async (input) => {
    const url = String(input);
    requests.push(url);
    if (url.endsWith("/screenshot")) {
      return new Response(JSON.stringify({ url: "https://storage.test/signed/feedback.png", expires_in: 60 }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }
    return new Response(JSON.stringify([{
      id: "feedback-attachment",
      surface: "global",
      category: "bug_report",
      response: null,
      reason: null,
      comment: "Layout issue",
      priority: "normal",
      has_screenshot: true,
      created_at: "2026-07-12T20:00:00Z",
      updated_at: "2026-07-12T20:00:00Z",
      submitted_by_profile_id: "athlete-1",
      submitter_email: "athlete@example.com",
      submitter_name: "Athlete One",
      contact_allowed: false,
      plan_id: null,
      today_checkin_id: null,
      camp_phase: null,
      app_version: "test",
      screenshot_expires_at: "2026-10-10T20:00:00Z",
    }]), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };

  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  try {
    await act(async () => {
      root.render(<AdminFeedbackPanel token="admin-token" reloadKey={0} />);
      await Promise.resolve();
      await Promise.resolve();
    });
    const button = Array.from(container.querySelectorAll("button")).find((item) =>
      item.textContent?.includes("View private screenshot"),
    );
    assert.ok(button);
    await act(async () => {
      button.click();
      await Promise.resolve();
      await Promise.resolve();
    });
    assert.ok(requests.some((url) => url.endsWith("/api/admin/feedback/feedback-attachment/screenshot")));
    const link = container.querySelector<HTMLAnchorElement>('a[href="https://storage.test/signed/feedback.png"]');
    assert.equal(link?.textContent, "Open private screenshot");
  } finally {
    globalThis.fetch = originalFetch;
    act(() => root.unmount());
    container.remove();
  }
});
