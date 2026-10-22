import assert from "node:assert/strict";
import test from "node:test";
import "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { NextIntlClientProvider } from "next-intl";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";
import { PathnameContext } from "next/dist/shared/lib/hooks-client-context.shared-runtime";
import messages from "../messages/en.json";
import { AppSessionContext } from "./auth-provider";
import { AppNav } from "./app-nav";

test("menu survives same-account session refresh but closes for route, account and sign-out changes", async () => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const router = { push() {}, replace() {}, refresh() {}, back() {}, forward() {}, prefetch() {}, bfcacheId: "fixture" };
  const settle = async (ms = 40) => act(async () => { await new Promise(resolve => setTimeout(resolve, ms)); });
  const render = async (user: string | null, token: string, pathname = "/plans") => {
    await act(async () => root.render(
      <NextIntlClientProvider locale="en" timeZone="Europe/London" messages={messages}>
        <AppRouterContext.Provider value={router}>
          <PathnameContext.Provider value={pathname}>
            <AppSessionContext.Provider value={{ isReady: true, isMeHydrated: true, hasTransientMeError: false,
              session: user ? { user_id: user, access_token: token } : null, me: null,
              previewAppearanceMode() {}, refreshMe: async () => {}, replaceMe() {}, signOut: async () => {} }}>
              <AppNav />
            </AppSessionContext.Provider>
          </PathnameContext.Provider>
        </AppRouterContext.Provider>
      </NextIntlClientProvider>,
    ));
    await settle();
  };
  const state = () => host.querySelector("#app-sidebar")?.getAttribute("data-mobile-nav-state");
  const open = async () => {
    const button = host.querySelector<HTMLButtonElement>('[aria-label="Open navigation"]');
    assert.ok(button);
    await act(async () => button.click());
    await settle();
    assert.equal(state(), "open");
  };
  try {
    await render("athlete-a", "token-a");
    await open();
    await render("athlete-a", "refreshed-token-a");
    assert.equal(state(), "open");
    await render("athlete-b", "token-b");
    await settle(260);
    assert.equal(state(), "closed");
    await open();
    await render("athlete-b", "token-b", "/history");
    await settle(260);
    assert.equal(state(), "closed");
    await open();
    await render(null, "", "/history");
    await settle(260);
    assert.equal(state(), "closed");
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});

test("phone bar links + Create to /create and the avatar to Settings", async () => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const router = { push() {}, replace() {}, refresh() {}, back() {}, forward() {}, prefetch() {}, bfcacheId: "fixture" };
  try {
    await act(async () => root.render(
      <NextIntlClientProvider locale="en" timeZone="Europe/London" messages={messages}>
        <AppRouterContext.Provider value={router}>
          <PathnameContext.Provider value="/today">
            <AppSessionContext.Provider value={{ isReady: true, isMeHydrated: true, hasTransientMeError: false,
              session: { user_id: "athlete-a", access_token: "token-a" }, me: null,
              previewAppearanceMode() {}, refreshMe: async () => {}, replaceMe() {}, signOut: async () => {} }}>
              <AppNav />
            </AppSessionContext.Provider>
          </PathnameContext.Provider>
        </AppRouterContext.Provider>
      </NextIntlClientProvider>,
    ));
    assert.equal(host.querySelector(".phone-create-button")?.getAttribute("href"), "/create");
    assert.equal(host.querySelector(".phone-account-button")?.getAttribute("href"), "/settings");
  } finally {
    await act(async () => root.unmount());
    host.remove();
  }
});
