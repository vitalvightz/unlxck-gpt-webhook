import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { DaySessionContext, SessionlessDayCard } from "./structured-plan-renderer";
import type { StructuredDay } from "@/lib/types";

function sessionlessTechnicalDay(headline: string): StructuredDay {
  return {
    date: "2026-08-16",
    countdown_label: "D-17",
    day_type: "moderate",
    today_card: {
      headline,
      readiness_status: "train_as_planned",
    },
    sessions: [],
  } as StructuredDay;
}

test("generic D-17 technical-only cards use the fight-intensity title", () => {
  const html = renderToStaticMarkup(
    <SessionlessDayCard day={sessionlessTechnicalDay("Technical-only combat")} />,
  );

  assert.equal(html.includes('<h3 class="sp-session-title">Fight-intensity technical rounds'), true);
});

test("countdown-specific converted sparring titles survive the technical renderer", () => {
  for (const title of [
    "Fight-intensity technical rounds",
    "Technical rhythm only",
    "Technical touch — pads / shadow",
    "Technical activation — no contact",
  ]) {
    const html = renderToStaticMarkup(
      <SessionlessDayCard day={sessionlessTechnicalDay(title)} />,
    );

    assert.equal(
      html.includes(`<h3 class="sp-session-title">${title}`),
      true,
      `expected renderer to preserve ${title}`,
    );
  }
});

test("converted sparring title also survives when contact shares a day with app work", () => {
  const day = {
    date: "2026-08-26",
    countdown_label: "D-7",
    day_type: "moderate",
    today_card: {
      headline: "Fight-week freshness",
      readiness_status: "train_as_planned",
      coach_led_contact: "Technical rhythm only",
    },
    sessions: [
      {
        session_id: "freshness-1",
        session_type: "mobility",
        title: "Fight-week freshness",
        blocks: [],
      },
    ],
  } as StructuredDay;

  const html = renderToStaticMarkup(<DaySessionContext day={day} />);

  assert.equal(
    html.includes('<p class="sp-today-headline">Technical rhythm only'),
    true,
  );
});
