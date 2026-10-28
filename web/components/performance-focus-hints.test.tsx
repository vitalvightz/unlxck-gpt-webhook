import assert from "node:assert/strict";
import test from "node:test";
import { window } from "./test-dom";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { NextIntlClientProvider } from "next-intl";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";
import { PathnameContext, SearchParamsContext } from "next/dist/shared/lib/hooks-client-context.shared-runtime";
import { AppSessionContext } from "./auth-provider";
import { PlanIntakeForm } from "./plan-intake-form";
import { QuickBuildForm } from "./quick-build-form";
import { emptyPlanRequest } from "@/lib/onboarding";
import messages from "../messages/en.json";
import type { MeResponse } from "@/lib/types";

async function mountFocus(quick: boolean, weakAreas: string[], goals = ["conditioning"]) {
  const oldFrame = globalThis.requestAnimationFrame, oldScroll = window.HTMLElement.prototype.scrollIntoView;
  globalThis.requestAnimationFrame = window.requestAnimationFrame.bind(window);
  window.HTMLElement.prototype.scrollIntoView = () => {};
  const host = document.createElement("div"); document.body.appendChild(host); const root = createRoot(host);
  const draft = { ...emptyPlanRequest(), current_step: 4, no_scheduled_fight: true, weak_areas: weakAreas, primary_weak_area: weakAreas[0] ?? "", key_goals: goals, primary_goal: goals[0] ?? "" };
  const me = { profile: { athlete_id: "fixture", full_name: "Alex", role: "athlete", athlete_timezone: "UTC", health_consent_granted: true, onboarding_draft: draft }, latest_intake: null } as unknown as MeResponse;
  const router = { push() {}, replace() {}, refresh() {}, back() {}, forward() {}, prefetch() {}, bfcacheId: "fixture" };
  await act(async () => root.render(
    <NextIntlClientProvider locale="en" timeZone="UTC" messages={messages}>
      <AppRouterContext.Provider value={router}><PathnameContext.Provider value={quick ? "/quick-build" : "/onboarding"}><SearchParamsContext.Provider value={new URLSearchParams()}>
        <AppSessionContext.Provider value={{ isReady: true, isMeHydrated: true, hasTransientMeError: false, session: { access_token: "token" } as never,
          me, previewAppearanceMode() {}, refreshMe: async () => {}, replaceMe() {}, signOut: async () => {} }}>
          {quick ? <QuickBuildForm /> : <PlanIntakeForm />}
        </AppSessionContext.Provider>
      </SearchParamsContext.Provider></PathnameContext.Provider></AppRouterContext.Provider>
    </NextIntlClientProvider>,
  ));
  const option = (name: string, weak = true) => {
    const group = [...host.querySelectorAll<HTMLElement>(".field")].find(field => (weak ? /^Weak [Aa]reas/ : /^Key [Gg]oals/).test(field.querySelector(":scope > .checkbox-group-label")?.textContent ?? ""));
    assert.ok(group);
    const label = [...group.querySelectorAll("label")].find(label => label.querySelector(".checkbox-card-title")?.textContent?.trim() === name);
    assert.ok(label, name); return { label, input: label.querySelector<HTMLInputElement>("input")! };
  };
  return { option, host, cleanup: async () => {
    await act(async () => root.unmount()); host.remove(); window.HTMLElement.prototype.scrollIntoView = oldScroll;
    if (oldFrame) globalThis.requestAnimationFrame = oldFrame; else Reflect.deleteProperty(globalThis, "requestAnimationFrame");
  } };
}

for (const quick of [false, true]) {
  test(`${quick ? "Quick Build" : "Camp Setup"} caps open plans at four combined picks and permits swapping a selected goal`, async () => {
    const ui = await mountFocus(quick, ["strength", "balance"], ["conditioning", "power"]);
    try {
      assert.match(ui.host.textContent ?? "", quick ? /shared cap: 4/ : /4 of 4 picks used/);
      assert.equal(ui.option("Recovery", false).input.disabled, true);
      assert.equal(ui.option("Conditioning", false).input.disabled, false);
      await act(async () => ui.option("Conditioning", false).input.click());
      assert.equal(ui.option("Recovery", false).input.disabled, false);
      await act(async () => ui.option("Recovery", false).input.click());
      assert.equal(ui.option("Recovery", false).input.checked, true);
      assert.equal(ui.option("Conditioning", false).input.disabled, true);
    } finally { await ui.cleanup(); }
  });
  test(`${quick ? "Quick Build" : "Camp Setup"} shows the reason immediately at two weak areas, and clears it when one is removed`, async () => {
    const ui = await mountFocus(quick, []);
    try {
      await act(async () => ui.option("Strength").input.click());
      assert.equal(ui.option("Gas Tank").input.disabled, false);
      await act(async () => ui.option("Balance").input.click());
      assert.equal(ui.option("Gas Tank").input.disabled, true);
      assert.ok(ui.option("Gas Tank").label.querySelector('button[aria-label="Why Gas Tank is unavailable"]'));
      assert.equal(ui.option("Strength").input.disabled, false);
      await act(async () => ui.option("Gas Tank").input.click());
      assert.equal(ui.option("Gas Tank").input.checked, false);
      await act(async () => ui.option("Balance").input.click());
      assert.equal(ui.option("Gas Tank").input.disabled, false);
      assert.equal(ui.option("Gas Tank").label.querySelector(".why-tooltip"), null);
    } finally { await ui.cleanup(); }
  });
  test(`${quick ? "Quick Build" : "Camp Setup"} restores cap explanations with a saved pair of weak areas`, async () => {
    const ui = await mountFocus(quick, ["strength", "balance"]);
    try {
      assert.equal(ui.option("Gas Tank").input.disabled, true);
      assert.ok(ui.option("Gas Tank").label.querySelector(".why-tooltip"));
      assert.equal(ui.option("Strength").input.checked, true);
    } finally { await ui.cleanup(); }
  });
}
