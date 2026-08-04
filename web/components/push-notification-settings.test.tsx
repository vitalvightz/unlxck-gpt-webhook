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

/** Stands in for the API, including the server-side master-switch cascade. */
function installFetchStub(): { patches: Preferences[] } {
  const patches: Preferences[] = [];
  let stored: Preferences = { ...DEFAULT_NOTIFICATION_PREFERENCES };

  globalThis.fetch = (async (input: unknown, init?: { method?: string; body?: string }) => {
    const url = String(input);
    if (url.includes("/api/push/preferences")) {
      const patch = JSON.parse(init?.body ?? "{}") as Preferences;
      patches.push({ ...patch });
      if (patch.push_enabled !== undefined) {
        for (const key of CATEGORY_KEYS) {
          if (patch[key] === undefined) patch[key] = Boolean(patch.push_enabled);
        }
      }
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

test("pausing the master switch turns every coaching category off", async () => {
  const { patches } = installFetchStub();
  const { container, root } = await mount();

  const master = toggles(container)[0];
  assert.equal(master.checked, true);
  assert.ok(categoryToggles(container).every((input) => input.checked));

  await click(master);

  assert.equal(master.checked, false);
  assert.ok(
    categoryToggles(container).every((input) => !input.checked),
    "every category row should follow the master switch off",
  );
  // The UI only sends the master switch; the server owns the cascade.
  assert.deepEqual(patches, [{ push_enabled: false }]);

  await act(async () => root.unmount());
});

test("category rows are locked while the account switch is paused", async () => {
  installFetchStub();
  const { container, root } = await mount();

  await click(toggles(container)[0]);
  assert.ok(
    categoryToggles(container).every((input) => input.disabled),
    "a paused account cannot arm a single category on its own",
  );

  await act(async () => root.unmount());
});

test("resuming the master switch turns the categories back on", async () => {
  installFetchStub();
  const { container, root } = await mount();

  const master = toggles(container)[0];
  await click(master);
  await click(master);

  assert.equal(master.checked, true);
  assert.ok(categoryToggles(container).every((input) => input.checked && !input.disabled));

  await act(async () => root.unmount());
});
