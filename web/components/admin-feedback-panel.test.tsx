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
      page_path: "/settings",
      device_context: "Desktop · Windows · Test Browser",
      language: "en-GB",
      readiness_context: [],
      injury_context: [],
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
      page_path: "/settings",
      device_context: "Desktop · Windows · Test Browser",
      language: "en-GB",
      readiness_context: [],
      injury_context: [],
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

test("admin feedback panel clears the previous token's rows while the new token's request is pending", async () => {
  const originalFetch = globalThis.fetch;
  const row = {
    id: "feedback-token-a",
    surface: "global",
    category: "general_feedback",
    response: null,
    reason: null,
    comment: "Visible only for token A",
    priority: "normal",
    has_screenshot: false,
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
    page_path: "/settings",
    device_context: "",
    language: "",
    readiness_context: [],
    injury_context: [],
    screenshot_expires_at: null,
  };
  globalThis.fetch = async (input, init) => {
    const auth = new Headers(init?.headers).get("authorization") ?? "";
    if (auth === "Bearer token-a") {
      return new Response(JSON.stringify([row]), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }
    return new Promise<Response>(() => {});
  };
  const { container, root } = mount();

  try {
    await act(async () => {
      root.render(<AdminFeedbackPanel token="token-a" reloadKey={0} />);
    });
    await settle();
    assert.match(container.textContent ?? "", /Visible only for token A/);

    await act(async () => {
      root.render(<AdminFeedbackPanel token="token-b" reloadKey={0} />);
    });
    await settle();

    assert.doesNotMatch(container.textContent ?? "", /Visible only for token A/);
    assert.match(container.textContent ?? "", /Loading feedback/);
  } finally {
    globalThis.fetch = originalFetch;
    act(() => root.unmount());
    container.remove();
  }
});

test("admin feedback expands captured context when no comment was provided", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify([{
    id: "feedback-no-comment",
    surface: "daily_recommendation",
    category: "recommendation_fit",
    response: "yes",
    reason: null,
    comment: "",
    priority: "normal",
    has_screenshot: false,
    created_at: "2026-07-12T20:00:00Z",
    updated_at: "2026-07-12T20:00:00Z",
    submitted_by_profile_id: "athlete-1",
    submitter_email: "athlete@example.com",
    submitter_name: "Athlete One",
    contact_allowed: false,
    plan_id: "plan-1",
    today_checkin_id: "checkin-1",
    camp_phase: "SPP",
    app_version: "test",
    page_path: "/today",
    device_context: "Mobile · Android · Test Browser",
    language: "en-GB",
    readiness_context: ["Pain: none", "Recommendation State: train_as_planned"],
    injury_context: ["left shoulder · moderate · open"],
    screenshot_expires_at: null,
  }]), { status: 200, headers: { "content-type": "application/json" } });
  const { container, root } = mount();

  try {
    await act(async () => {
      root.render(<AdminFeedbackPanel token="admin-token" reloadKey={0} />);
    });
    await settle();

    assert.match(container.textContent ?? "", /No written comment\. Showing captured context\./);
    assert.match(container.textContent ?? "", /Submission context/);
    assert.match(container.textContent ?? "", /\/today/);
    assert.match(container.textContent ?? "", /plan-1/);
    assert.match(container.textContent ?? "", /checkin-1/);
    assert.match(container.textContent ?? "", /Pain: none/);
    assert.match(container.textContent ?? "", /left shoulder · moderate · open/);
    assert.ok(container.querySelector('section[aria-label="Submission context"]'));
  } finally {
    globalThis.fetch = originalFetch;
    act(() => root.unmount());
    container.remove();
  }
});
