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

test("admin feedback panel groups athlete responses and keeps raw technical context out of the review card", async () => {
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
      readiness_snapshot: {
        sleep: "good",
        body: "normal",
        pain: "none",
        active_injury: "none",
        recommendation_state: "train_as_planned",
      },
      injury_snapshot: { open_flags: [] },
      technical_context: {
        referer_path: "/today",
        device_platform: '"Windows"',
        browser_brands: '"Not:A-Brand";v="8", "Chromium";v="150"',
        user_agent: "Desktop Windows full raw browser string",
        language: "en-GB,en;q=0.9",
      },
      app_version: "test-sha",
      has_screenshot: true,
      screenshot_expires_at: "2026-10-10T00:00:00Z",
      created_at: "2026-07-12T20:00:00Z",
      updated_at: "2026-07-12T20:00:00Z",
    },
    {
      id: "feedback-2",
      submitted_by_profile_id: "profile-1",
      submitter_email: "athlete@example.com",
      submitter_name: "",
      surface: "daily_recommendation",
      category: "recommendation_fit",
      response: "yes",
      reason: null,
      comment: "",
      contact_allowed: false,
      priority: "normal",
      plan_id: "plan-1",
      today_checkin_id: "checkin-1",
      camp_phase: "SPP",
      readiness_snapshot: { sleep: "good", body: "normal", pain: "none" },
      injury_snapshot: { open_flags: [] },
      technical_context: {},
      app_version: "local",
      has_screenshot: false,
      screenshot_expires_at: null,
      created_at: "2026-07-12T19:00:00Z",
      updated_at: "2026-07-12T19:00:00Z",
    },
    {
      id: "feedback-3",
      submitted_by_profile_id: "profile-1",
      submitter_email: "athlete@example.com",
      submitter_name: "",
      surface: "plan",
      category: "plan_usefulness",
      response: "no",
      reason: "instructions_unclear",
      comment: "",
      contact_allowed: false,
      priority: "normal",
      plan_id: "plan-1",
      today_checkin_id: null,
      camp_phase: "GPP",
      readiness_snapshot: {},
      injury_snapshot: { open_flags: [] },
      technical_context: {},
      app_version: "local",
      has_screenshot: false,
      screenshot_expires_at: null,
      created_at: "2026-07-12T18:00:00Z",
      updated_at: "2026-07-12T18:00:00Z",
    },
  ]), { status: 200, headers: { "content-type": "application/json" } });
  const { container, root } = mount();

  try {
    await act(async () => {
      root.render(<AdminFeedbackPanel token="admin-token" reloadKey={0} />);
    });
    await settle();

    assert.match(container.textContent ?? "", /Feedback review/);
    assert.match(container.textContent ?? "", /Safety report/);
    assert.match(container.textContent ?? "", /Authenticated user/);
    assert.equal((container.textContent ?? "").match(/athlete@example\.com/g)?.length, 1);
    assert.match(container.textContent ?? "", /3 recent responses/);
    assert.match(container.textContent ?? "", /Positive feedback/);
    assert.match(container.textContent ?? "", /Negative feedback/);
    assert.match(container.textContent ?? "", /Instructions unclear/);
    assert.deepEqual(
      Array.from(container.querySelectorAll(".admin-feedback-response"), (element) => element.textContent),
      ["REPORT", "POSITIVE", "NEGATIVE"],
    );
    assert.match(container.textContent ?? "", /Good sleep/);
    assert.match(container.textContent ?? "", /Recommendation: Train as planned/);
    assert.match(container.textContent ?? "", /Windows/);
    assert.match(container.textContent ?? "", /Chromium/);
    assert.doesNotMatch(container.textContent ?? "", /Desktop Windows full raw browser string/);
    assert.match(container.textContent ?? "", /Athlete permits follow-up/);
    assert.match(container.textContent ?? "", /View screenshot/);
    assert.match(container.textContent ?? "", /View check-in/);
    assert.match(container.textContent ?? "", /Open plan/);
    assert.match(container.textContent ?? "", /Open athlete/);
    assert.ok(Array.from(container.querySelectorAll("details")).every((details) => !details.open));
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
      readiness_snapshot: {},
      injury_snapshot: {},
      technical_context: {},
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
      item.textContent?.includes("View screenshot"),
    );
    assert.ok(button);
    await act(async () => {
      button.click();
      await Promise.resolve();
      await Promise.resolve();
    });
    assert.ok(requests.some((url) => url.endsWith("/api/admin/feedback/feedback-attachment/screenshot")));
    const link = container.querySelector<HTMLAnchorElement>('a[href="https://storage.test/signed/feedback.png"]');
    assert.equal(link?.textContent, "Open screenshot");
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
    readiness_snapshot: {},
    injury_snapshot: {},
    technical_context: {},
    app_version: "test",
    screenshot_expires_at: null,
  };
  globalThis.fetch = async (_input, init) => {
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
