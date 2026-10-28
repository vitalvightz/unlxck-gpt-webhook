import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";

import { AppSessionContext } from "./auth-provider";
import { StartingPathScreen } from "./starting-path-screen";

const router = { push() {}, replace() {}, refresh() {}, back() {}, forward() {}, prefetch() {}, bfcacheId: "fixture" };
const me = {
  profile: {
    role: "athlete", starting_path: null, onboarding_draft: {}, technical_style: [],
    date_of_birth: "1990-01-01", meets_minimum_age: true, terms_accepted: true, is_minor: false,
  },
  plan_count: 0,
  latest_plan: null,
  latest_intake: null,
};

test("the optional analytics choice is reachable before a starting path leaves the screen", () => {
  const html = renderToStaticMarkup(
    <AppRouterContext.Provider value={router as never}>
      <AppSessionContext.Provider value={{ session: { access_token: "t" }, me, isMeHydrated: true, hasTransientMeError: false } as never}>
        <StartingPathScreen />
      </AppSessionContext.Provider>
    </AppRouterContext.Provider>,
  );
  const consent = html.indexOf("Allow optional feature analytics");
  // Each starting-path choice saves and navigates at once; the choice must come first and be visible.
  assert.ok(consent > 0 && consent < html.indexOf("Generate my S&amp;C plan"));
  assert.match(html, /<details open=""><summary>Optional product analytics/);
  // Still default-off: never checked before the athlete chooses.
  assert.doesNotMatch(html, /type="checkbox"[^>]*checked/);
});
