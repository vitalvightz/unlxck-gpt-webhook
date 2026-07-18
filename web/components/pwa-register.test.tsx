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
  window.history.replaceState({}, "", "/");
}

async function settle(durationMs = 20) {
  await act(async () => {
    await new Promise((resolve) => window.setTimeout(resolve, durationMs));
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

function renderInstallSurface(
  root: Root,
  environment?: string,
  reloadPage?: () => void,
) {
  root.render(
    <ToastProvider>
      <PwaRegister environment={environment} reloadPage={reloadPage}>
        <InstallUnlxck />
      </PwaRegister>
    </ToastProvider>,
  );
}

function mockServiceWorker() {
  const originalDescriptor = Object.getOwnPropertyDescriptor(navigator, "serviceWorker");
  const controllerChangeListeners = new Set<() => void>();
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
    addEventListener: (type: string, listener: () => void) => {
      if (type === "controllerchange") controllerChangeListeners.add(listener);
    },
    removeEventListener: (type: string, listener: () => void) => {
      if (type === "controllerchange") controllerChangeListeners.delete(listener);
    },
  };
  Object.defineProperty(navigator, "serviceWorker", {
    configurable: true,
    value: serviceWorker,
  });

  return {
    dispatchControllerChange: () => controllerChangeListeners.forEach((listener) => listener()),
    postedMessages,
    restore: () => {
      if (originalDescriptor) {
        Object.defineProperty(navigator, "serviceWorker", originalDescriptor);
      } else {
        Reflect.deleteProperty(navigator, "serviceWorker");
      }
    },
  };
}

test("unsupported browsers do not see a misleading Settings install panel", async () => {
  setMatchMedia(false);
  const { container, root } = mount();
  try {
    await act(async () => renderInstallSurface(root));
    assert.equal(container.querySelector('[data-testid="install-unlxck"]'), null);
    await settle();
    assert.equal(container.querySelector('[data-testid="install-unlxck"]'), null);
    assert.doesNotMatch(container.textContent ?? "", /browser menu|install app/i);
  } finally {
    cleanup(container, root);
  }
});

test("install state renders nothing while capability detection is pending", async () => {
  setMatchMedia(false);
  const { container, root } = mount();
  try {
    await act(async () => renderInstallSurface(root));
    assert.equal(container.querySelector('[data-testid="install-unlxck"]'), null);
  } finally {
    cleanup(container, root);
  }
});

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

test("iPhone Settings action shows only the Safari Add to Home Screen flow", async () => {
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
    const trigger = Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find(
      (button) => button.textContent === "View iPhone steps",
    );
    assert.ok(trigger);
    await act(async () => trigger.click());
    const dialog = container.querySelector<HTMLElement>('[role="dialog"]');
    const dialogText = dialog?.textContent ?? "";
    assert.match(dialogText, /Open the Share menu/);
    assert.match(dialogText, /Select “Add to Home Screen”/);
    assert.match(dialogText, /Tap “Add”/);
    assert.doesNotMatch(dialogText, /browser menu|Install app/i);

    const close = dialog?.querySelector<HTMLButtonElement>(
      '[aria-label="Close install instructions"]',
    );
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

    const outsideButton = document.createElement("button");
    document.body.appendChild(outsideButton);
    outsideButton.focus();
    await act(async () => {
      window.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Tab" }));
    });
    assert.equal(document.activeElement, close);
    outsideButton.remove();
  } finally {
    cleanup(container, root);
    if (userAgentDescriptor) Object.defineProperty(navigator, "userAgent", userAgentDescriptor);
    else Reflect.deleteProperty(navigator, "userAgent");
    if (touchDescriptor) Object.defineProperty(navigator, "maxTouchPoints", touchDescriptor);
    else Reflect.deleteProperty(navigator, "maxTouchPoints");
  }
});

test("captured Chromium install prompt is used only after an explicit click", async () => {
  setMatchMedia(false);
  let promptCalls = 0;
  const { container, root } = mount();
  try {
    await act(async () => renderInstallSurface(root));
    await settle();
    assert.equal(container.querySelector('[data-testid="install-unlxck"]'), null);

    const event = Object.assign(new window.Event("beforeinstallprompt", { cancelable: true }), {
      prompt: async () => {
        promptCalls += 1;
      },
      userChoice: Promise.resolve({ outcome: "accepted" as const, platform: "web" }),
    });
    await act(async () => window.dispatchEvent(event));

    const trigger = Array.from(container.querySelectorAll<HTMLButtonElement>("button")).find(
      (button) => button.textContent === "Install UNLXCK",
    );
    assert.ok(trigger);
    assert.equal(promptCalls, 0);
    await act(async () => trigger.click());
    await settle();
    assert.equal(promptCalls, 1);
    await act(async () => window.dispatchEvent(new window.Event("appinstalled")));
    await settle();
    assert.equal(container.querySelector('[data-testid="install-unlxck"]'), null);
  } finally {
    cleanup(container, root);
  }
});

test("a rejected native prompt hides the panel instead of inventing manual steps", async () => {
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
    assert.equal(container.querySelector('[data-testid="install-unlxck"]'), null);
    assert.equal(container.querySelector('[role="dialog"]'), null);
  } finally {
    cleanup(container, root);
  }
});

test("waiting updates defer on critical routes and return with a Refresh action on safe routes", async () => {
  setMatchMedia(false);
  window.history.replaceState({}, "", "/generate");
  const worker = mockServiceWorker();
  const { container, root } = mount();
  try {
    await act(async () => renderInstallSurface(root, "production", () => {}));
    await settle();
    assert.doesNotMatch(container.textContent ?? "", /New version available/);
    assert.deepEqual(worker.postedMessages, []);

    window.history.pushState({}, "", "/dashboard");
    await act(async () => window.dispatchEvent(new window.PopStateEvent("popstate")));
    await settle();
    assert.match(container.textContent ?? "", /New version available/);
    assert.equal(container.querySelector<HTMLButtonElement>(".toast-action")?.textContent, "Refresh");
  } finally {
    cleanup(container, root);
    worker.restore();
  }
});

test("unsaved input hides an update action until navigation reaches a safe route", async () => {
  setMatchMedia(false);
  const worker = mockServiceWorker();
  const { container, root } = mount();
  try {
    await act(async () => renderInstallSurface(root, "production", () => {}));
    await settle();
    assert.ok(container.querySelector(".toast-action"));

    const input = document.createElement("input");
    container.appendChild(input);
    await act(async () => input.dispatchEvent(new window.Event("input", { bubbles: true })));
    await settle();
    assert.equal(container.querySelector(".toast-action"), null);

    window.history.pushState({}, "", "/today");
    await act(async () => window.dispatchEvent(new window.PopStateEvent("popstate")));
    await settle();
    assert.equal(container.querySelector<HTMLButtonElement>(".toast-action")?.textContent, "Refresh");
  } finally {
    cleanup(container, root);
    worker.restore();
  }
});

test("controller changes never reload automatically and explicit refresh reloads only once", async () => {
  setMatchMedia(false);
  const worker = mockServiceWorker();
  let reloadCalls = 0;
  const { container, root } = mount();
  try {
    await act(async () =>
      renderInstallSurface(root, "production", () => {
        reloadCalls += 1;
      }),
    );
    await settle();

    worker.dispatchControllerChange();
    assert.equal(reloadCalls, 0);

    const refresh = container.querySelector<HTMLButtonElement>(".toast-action");
    assert.ok(refresh);
    await act(async () => refresh.click());
    assert.deepEqual(worker.postedMessages, [{ type: "SKIP_WAITING" }]);

    worker.dispatchControllerChange();
    worker.dispatchControllerChange();
    assert.equal(reloadCalls, 1);
  } finally {
    cleanup(container, root);
    worker.restore();
  }
});
