import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { SessionlessDayCard } from "../components/structured-plan-renderer";
import { stripSafetyOwnedStopRules } from "./block-display-guardrails";
import type { StructuredDay } from "./types";

test("a TRX control criterion survives deduplicated safety", () => {
  const rules = ["Stop if joint pain or pelvis dropping."];
  const safety = ["Stop for pain."];
  assert.deepEqual(stripSafetyOwnedStopRules(rules, safety), rules);
});

test("declared and converted technical days have context info", () => {
  const card = (date: string, headline: string, focus: string) => ({
    date, weekday: "Thu", countdown_label: "D-9",
    today_card: { headline, mindset_anchor: {
      intent: "Controlled work", focus_cue: focus, reset_cue: "Reset between rounds",
    } }, sessions: [],
  }) as unknown as StructuredDay;
  const declared = renderToStaticMarkup(
    <SessionlessDayCard day={card("2026-11-26", "Light Combat / Technical", "Stay smooth")} />,
  );
  const converted = renderToStaticMarkup(
    <SessionlessDayCard day={card("2026-11-28", "Technical-only combat", "Stay light")} />,
  );
  assert.match(declared, /info-tooltip/);
  assert.match(converted, /info-tooltip/);
});
