import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { TodayRiskWatch } from "./today-risk-watch";
import type { TodayCommandView } from "@/lib/types";

const HISTORICAL_PAIN: TodayCommandView["risk_watch"][number] = {
  category: "high_pain",
  priority: 3,
  icon: "alert-triangle",
  label: "High pain",
  text: "Pain was logged at 8/10. Reassess before your next session.",
  tone: "warning",
  timeframe: "last_session",
};

function render(hasActiveInjury: boolean): string {
  return renderToStaticMarkup(
    <TodayRiskWatch risks={[HISTORICAL_PAIN]} hasActiveInjury={hasActiveInjury} />,
  );
}

test("historical pain names its timing and links to add an injury when none is active", () => {
  const html = render(false);
  assert.match(html, /Last session/);
  assert.match(html, /Pain was logged at 8\/10/);
  assert.match(html, /Still present\? Add an injury\./);
  assert.match(html, /href="#today-injury"/);
  assert.doesNotMatch(html, /Update your injury/);
});

test("historical pain links to update when any active injury exists", () => {
  const html = render(true);
  assert.match(html, /Still present\? Update your injury\./);
  assert.doesNotMatch(html, /Add an injury/);
});

test("current risks do not invent an injury action", () => {
  const current: TodayCommandView["risk_watch"][number] = {
    ...HISTORICAL_PAIN,
    text: "High pain reported during today's check-in.",
    timeframe: "today",
  };
  const html = renderToStaticMarkup(<TodayRiskWatch risks={[current]} />);
  assert.match(html, /Today/);
  assert.doesNotMatch(html, /Still present/);
  assert.doesNotMatch(html, /href="#today-injury"/);
});
