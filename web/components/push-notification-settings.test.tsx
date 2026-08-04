import test from "node:test";
import assert from "node:assert/strict";

// Installs the jsdom globals for react-dom/client (import side effect).
import "./test-dom";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import { PushNotificationSettings } from "./push-notification-settings";
import { DEFAULT_NOTIFICATION_PREFERENCES } from "@/lib/notification-preferences";

const CATEGORY_KEYS = [
  "session_reminders",
  "checkin_reminders",
  "injury_followups",
  "plan_update_alerts",
  "progress_milestones",
  "coach_messages",
] as const;

type Preferences = Record<string, unknown>;

/** Stands in for the API: a patch merges into the stored preferences, nothing else. */
function installFetchStub(overrides: Preferences = {}): { patches: Preferences[] } {
  const patches: Preferences[] = [];
  let stored: Preferences = { ...DEFAULT_NOTIFICATION_PREFERENCES, ...overrides };

  globalThis.fetch = (async (input: unknown, init?: { method?: string; body?: string }) => {
    const url = String(input);
    if (url.includes("/api/push/preferences")) {
      const patch = JSON.parse(init?.body ?? "{}") as Preferences;
      patches.push({ ...patch });
      stored = { ...stored, ...patch };
      return new Response(JSON.stringify(stored), { status: 200 });
    }
    if (url.includes("/api/push/settings")) {
      return new Response(JSON.stringify({ enabled: true, public_key: "k", preferences: stored }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    throw new Error(`unexpected fetch: ${url}`);
  }) as typeof fetch;

  return { patches };
}

function toggles(container: HTMLElement): HTMLInputElement[] {
  return Array.from(
    container.querySelectorAll<HTMLInputElement>(".settings-server-notification-list input[type=checkbox]"),
  );
}

/** Master switch first, then one row per coaching category. */
function categoryToggles(container: HTMLElement): HTMLInputElement[] {
  return toggles(container).slice(1, 1 + CATEGORY_KEYS.length);
}

async function mount(): Promise<{ container: HTMLElement; root: Root }> {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<PushNotificationSettings token="test-token" />);
  });
  return { container, root };
}

async function click(input: HTMLInputElement): Promise<void> {
  await act(async () => {
    input.click();
  });
}

test("pausing the master switch reads as every coaching category off", async () => {
  const { patches } = installFetchStub();
  const { container, root } = await mount();

  const master = toggles(container)[0];
  assert.equal(master.checked, true);
  assert.ok(categoryToggles(container).every((input) => input.checked));

  await click(master);

  assert.equal(master.checked, false);
  assert.ok(
    categoryToggles(container).every((input) => !input.checked && input.disabled),
    "every category row should read as off and locked while the account is paused",
  );
  // Only the master switch is written; the stored category choices are untouched.
  assert.deepEqual(patches, [{ push_enabled: false }]);

  await act(async () => root.unmount());
});

test("resuming restores the athlete's own rows, not an all-on default", async () => {
  const { patches } = installFetchStub({ coach_messages: false });
  const { container, root } = await mount();

  const master = toggles(container)[0];
  const coachMessages = categoryToggles(container)[CATEGORY_KEYS.indexOf("coach_messages")];
  assert.equal(coachMessages.checked, false);

  await click(master);
  await click(master);

  assert.equal(master.checked, true);
  assert.equal(
    coachMessages.checked,
    false,
    "a category turned off before pausing must stay off after resuming",
  );
  assert.ok(
    categoryToggles(container)
      .filter((input) => input !== coachMessages)
      .every((input) => input.checked && !input.disabled),
  );
  assert.deepEqual(patches, [{ push_enabled: false }, { push_enabled: true }]);

  await act(async () => root.unmount());
});

test("an individual category still saves on its own while the account is live", async () => {
  const { patches } = installFetchStub();
  const { container, root } = await mount();

  await click(categoryToggles(container)[CATEGORY_KEYS.indexOf("injury_followups")]);

  assert.deepEqual(patches, [{ injury_followups: false }]);
  assert.equal(toggles(container)[0].checked, true);

  await act(async () => root.unmount());
});
