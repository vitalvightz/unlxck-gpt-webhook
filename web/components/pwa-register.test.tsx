import assert from "node:assert/strict";
import test from "node:test";

import "./test-dom";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";

import { InstallUnlxck } from "./install-unlxck";
import { PwaRegister } from "./pwa-register";
import { ToastProvider } from "./toast-provider";

function mount(): { container: HTMLElement; root: Root } {
  const container = document.createElement("div");
  document.body.appendChild(container);
  return { container, root: createRoot(container) };
}

function cleanup(container: HTMLElement, root: Root) {
  act(() => root.unmount());
  container.remove();
  document.body.innerHTML = "";
}

async function settle() {
  await act(async () => {
    await new Promise((resolve) => window.setTimeout(resolve, 20));
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
}

function setMatchMedia(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: () => ({
      matches,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  });
}

function renderInstallSurface(root: Root, environment?: string) {
  root.render(
    <ToastProvider>
      <PwaRegister environment={environment}>
        <InstallUnlxck />
      </PwaRegister>
    </ToastProvider>,
  );
}

test("installed standalone mode hides the Settings install action", async () => {
  setMatchMedia(true);
  const { container, root } = mount();
  try {
    await act(async () => renderInstallSurface(root));
    await settle();
    assert.equal(container.querySelector('[data-testid="install-unlxck"]'), null);
  } finally {
    cleanup(container, root);
  }
});

test("explicit Settings action opens restrained browser install instructions", async () => {
  setMatchMedia(false);
  const { container, root } = mount();
  try {
    await act(async () => renderInstallSurface(root));
    await settle();
    const trigger = Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find((button) =>
      button.textContent?.includes("View install steps"),
    );
    assert.ok(trigger);
    await act(async () => trigger.click());
    assert.equal(container.querySelector('[role="dialog"]')?.getAttribute("aria-modal"), "true");
    assert.match(container.querySelector('[role="dialog"]')?.textContent ?? "", /Choose “Install app”/);

    const dialog = container.querySelector<HTMLElement>('[role="dialog"]');
    const close = dialog?.querySelector<HTMLButtonElement>('[aria-label="Close install instructions"]');
    const done = Array.from(dialog?.querySelectorAll<HTMLButtonElement>("button") ?? []).find(
      (button) => button.textContent === "Done",
    );
    assert.ok(close);
    assert.ok(done);
    assert.equal(document.activeElement, close);
    await act(async () => {
      window.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Tab", shiftKey: true }));
    });
    assert.equal(document.activeElement, done);
    await act(async () => {
      window.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Tab" }));
    });
    assert.equal(document.activeElement, close);
  } finally {
    cleanup(container, root);
  }
});

test("iPhone Settings action shows the truthful Safari Add to Home Screen flow", async () => {
  setMatchMedia(false);
  const userAgentDescriptor = Object.getOwnPropertyDescriptor(navigator, "userAgent");
  const touchDescriptor = Object.getOwnPropertyDescriptor(navigator, "maxTouchPoints");
  Object.defineProperty(navigator, "userAgent", {
    configurable: true,
    value: "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)",
  });
  Object.defineProperty(navigator, "maxTouchPoints", { configurable: true, value: 5 });
  const { container, root } = mount();
  try {
    await act(async () => renderInstallSurface(root));
    await settle();
    const trigger = Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find((button) =>
      button.textContent === "View iPhone steps",
    );
    assert.ok(trigger);
    await act(async () => trigger.click());
    const dialogText = container.querySelector('[role="dialog"]')?.textContent ?? "";
    assert.match(dialogText, /Open the Share menu/);
    assert.match(dialogText, /Select “Add to Home Screen”/);
    assert.match(dialogText, /Tap “Add”/);
  } finally {
    cleanup(container, root);
    if (userAgentDescriptor) {
      Object.defineProperty(navigator, "userAgent", userAgentDescriptor);
    } else {
      Reflect.deleteProperty(navigator, "userAgent");
    }
    if (touchDescriptor) {
      Object.defineProperty(navigator, "maxTouchPoints", touchDescriptor);
    } else {
      Reflect.deleteProperty(navigator, "maxTouchPoints");
    }
  }
});

test("captured Chromium install prompt is used only after the explicit install click", async () => {
  setMatchMedia(false);
  let promptCalls = 0;
  const { container, root } = mount();
  try {
    await act(async () => renderInstallSurface(root));
    await settle();

    const event = Object.assign(new window.Event("beforeinstallprompt", { cancelable: true }), {
      prompt: async () => {
        promptCalls += 1;
      },
      userChoice: Promise.resolve({ outcome: "accepted" as const, platform: "web" }),
    });
    await act(async () => window.dispatchEvent(event));

    const trigger = Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find((button) =>
      button.textContent === "Install UNLXCK",
    );
    assert.ok(trigger);
    assert.equal(promptCalls, 0);
    await act(async () => trigger.click());
    await settle();
    assert.equal(promptCalls, 1);
    assert.ok(container.querySelector('[data-testid="install-unlxck"]'));
    await act(async () => window.dispatchEvent(new window.Event("appinstalled")));
    await settle();
    assert.equal(container.querySelector('[data-testid="install-unlxck"]'), null);
  } finally {
    cleanup(container, root);
  }
});

test("a rejected native prompt falls back to the manual install guide", async () => {
  setMatchMedia(false);
  const { container, root } = mount();
  try {
    await act(async () => renderInstallSurface(root));
    await settle();
    const event = Object.assign(new window.Event("beforeinstallprompt", { cancelable: true }), {
      prompt: async () => {
        throw new Error("stale install prompt");
      },
      userChoice: Promise.resolve({ outcome: "dismissed" as const, platform: "web" }),
    });
    await act(async () => window.dispatchEvent(event));
    const trigger = Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find(
      (button) => button.textContent === "Install UNLXCK",
    );
    assert.ok(trigger);
    await act(async () => trigger.click());
    await settle();
    assert.ok(container.querySelector('[role="dialog"]'));
  } finally {
    cleanup(container, root);
  }
});

test("a waiting service worker surfaces the controlled refresh action", async () => {
  setMatchMedia(false);
  const originalDescriptor = Object.getOwnPropertyDescriptor(navigator, "serviceWorker");
  const postedMessages: unknown[] = [];
  const waitingWorker = { postMessage: (message: unknown) => postedMessages.push(message) };
  const registration = {
    waiting: waitingWorker,
    installing: null,
    addEventListener: () => {},
    removeEventListener: () => {},
  };
  const serviceWorker = {
    controller: {},
    register: async () => registration,
    addEventListener: () => {},
    removeEventListener: () => {},
  };
  Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: serviceWorker });

  const { container, root } = mount();
  try {
    await act(async () => renderInstallSurface(root, "production"));
    await settle();
    assert.match(container.textContent ?? "", /New version available\./);
    const refresh = container.querySelector<HTMLButtonElement>(".toast-action");
    assert.ok(refresh);
    await act(async () => refresh.click());
    assert.deepEqual(postedMessages, [{ type: "SKIP_WAITING" }]);
  } finally {
    cleanup(container, root);
    if (originalDescriptor) {
      Object.defineProperty(navigator, "serviceWorker", originalDescriptor);
    } else {
      Reflect.deleteProperty(navigator, "serviceWorker");
    }
  }
});
