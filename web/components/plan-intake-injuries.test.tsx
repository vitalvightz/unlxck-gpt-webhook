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
import messages from "../messages/en.json";
import { emptyPlanRequest } from "@/lib/onboarding";
import { buildGuidedInjuryFields, EMPTY_GUIDED_INJURY, type GuidedInjuryState } from "@/lib/guided-injury";
import type { MeResponse } from "@/lib/types";

async function mountInjuries(injuries: GuidedInjuryState[] = []) {
  const originalScrollTo = window.scrollTo;
  const originalFrame = globalThis.requestAnimationFrame;
  const originalScrollIntoView = window.HTMLElement.prototype.scrollIntoView;
  window.scrollTo = () => {};
  globalThis.requestAnimationFrame = window.requestAnimationFrame.bind(window);
  window.HTMLElement.prototype.scrollIntoView = () => {};
  const draft = { ...emptyPlanRequest(), ...buildGuidedInjuryFields(injuries), current_step: 3 };
  const me = { profile: { id: "fixture-athlete", full_name: "Fixture athlete", role: "athlete",
    health_consent_granted: true, onboarding_draft: draft }, latest_intake: null } as unknown as MeResponse;
  const router = { push() {}, replace() {}, refresh() {}, back() {}, forward() {}, prefetch() {}, bfcacheId: "fixture" };
  const session = { isReady: true, isMeHydrated: true, hasTransientMeError: false,
    session: { access_token: "fixture-token" }, me, previewAppearanceMode() {}, refreshMe: async () => {},
    replaceMe() {}, signOut: async () => {} };
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => root.render(
    <NextIntlClientProvider locale="en" timeZone="Europe/London" messages={messages}>
      <AppRouterContext.Provider value={router}>
        <PathnameContext.Provider value="/onboarding"><SearchParamsContext.Provider value={new URLSearchParams()}>
          <AppSessionContext.Provider value={session}><PlanIntakeForm /></AppSessionContext.Provider>
        </SearchParamsContext.Provider></PathnameContext.Provider>
      </AppRouterContext.Provider>
    </NextIntlClientProvider>,
  ));
  const press = async (text: string) => {
    const button = Array.from(host.querySelectorAll("button")).find((entry) => entry.textContent?.trim() === text);
    assert.ok(button, text);
    await act(async () => button.click());
  };
  return { host, press, cleanup: async () => {
    await act(async () => root.unmount()); host.remove();
    window.scrollTo = originalScrollTo;
    if (originalFrame) globalThis.requestAnimationFrame = originalFrame;
    else Reflect.deleteProperty(globalThis, "requestAnimationFrame");
    if (originalScrollIntoView) window.HTMLElement.prototype.scrollIntoView = originalScrollIntoView;
    else Reflect.deleteProperty(window.HTMLElement.prototype, "scrollIntoView");
  } };
}

test("actual onboarding reveals map, then one editor, then a saved row before adding another", async () => {
  const ui = await mountInjuries();
  try {
    await ui.press("+ Add an injury or restriction");
    assert.ok(ui.host.querySelector(".body-map-panel"));
    assert.equal(ui.host.querySelector(".injury-card-form"), null);
    assert.equal(ui.host.querySelector(".injury-card-add-row"), null);
    const shoulder = ui.host.querySelector('[aria-label="Left shoulder"]');
    assert.ok(shoulder);
    await act(async () => shoulder.dispatchEvent(new window.MouseEvent("click", { bubbles: true })));
    assert.equal(ui.host.querySelector(".body-map-panel"), null);
    assert.ok(ui.host.querySelector(".injury-card-form"));
    assert.equal(ui.host.querySelector(".injury-card-add-row"), null);
    await ui.press("Tightness");
    await ui.press("Limiting me");
    await ui.press("→ Stable");
    await ui.press("Save injury");
    assert.equal(ui.host.querySelector(".injury-card-form"), null);
    await ui.press("+ Add another injury");
    assert.ok(ui.host.querySelector(".body-map-panel"));
    assert.equal(ui.host.querySelector(".injury-card-form"), null);
    assert.equal(ui.host.querySelectorAll(".injury-card-streamlined").length, 1);
    assert.match(ui.host.textContent ?? "", /Tightness · Limiting me · Stable/);
  } finally { await ui.cleanup(); }
});

test("saved onboarding draft resumes its existing area without opening the map", async () => {
  const ui = await mountInjuries([{ ...EMPTY_GUIDED_INJURY, area: "Left knee", zone: "l_knee",
    injury_type: "tightness", severity: "moderate", trend: "stable", notes: "[training_impact:limiting]" }]);
  try {
    assert.equal(ui.host.querySelector(".body-map-panel"), null);
    assert.ok(ui.host.querySelector(".injury-card-form"));
    assert.match(ui.host.textContent ?? "", /Left knee/);
    assert.equal(ui.host.querySelector('[aria-pressed="true"].injury-severity-chip')?.textContent, "Limiting me");
    const change = ui.host.querySelector<HTMLButtonElement>('[aria-label="Change affected area for injury 1"]');
    assert.ok(change);
    await act(async () => change.click());
    assert.ok(ui.host.querySelector(".body-map-panel"));
    assert.equal(ui.host.querySelector(".injury-card-form"), null);
    const quad = ui.host.querySelector('[aria-label="Left quad"]');
    assert.ok(quad);
    await act(async () => quad.dispatchEvent(new window.MouseEvent("click", { bubbles: true })));
    assert.equal(ui.host.querySelector(".body-map-panel"), null);
    assert.equal(ui.host.querySelector(".injury-card-title")?.textContent, "Left quad");
    assert.equal(ui.host.querySelector('[aria-pressed="true"].injury-severity-chip')?.textContent, "Limiting me");
    await ui.press("Save injury");
    assert.equal(ui.host.querySelectorAll(".injury-card-streamlined").length, 1);
  } finally { await ui.cleanup(); }
});
