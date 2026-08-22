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

test("generic D-17 technical-only cards use the fight-intensity title and summary", () => {
  const html = renderToStaticMarkup(
    <SessionlessDayCard day={sessionlessTechnicalDay("Technical-only combat")} />,
  );

  assert.equal(html.includes('<h3 class="sp-session-title">Controlled fight-speed technical rounds'), true);
  assert.equal(
    html.includes("Realistic exchanges at speed, controlled contact, low total volume."),
    true,
  );
});

test("countdown-specific converted sparring titles keep their own short summaries", () => {
  const cases = [
    [
      "Controlled fight-speed technical rounds",
      "Realistic exchanges at speed, controlled contact, low total volume.",
    ],
    [
      "Technical rhythm only",
      "Light technical rounds. Prioritise timing, flow and clean execution.",
    ],
    [
      "Technical touch — pads / shadow",
      "Pads or shadow only. Stay sharp without contact fatigue.",
    ],
    [
      "Technical activation — no contact",
      "Brief movement and reactions. Finish feeling fresher than you started.",
    ],
  ] as const;

  for (const [title, summary] of cases) {
    const html = renderToStaticMarkup(
      <SessionlessDayCard day={sessionlessTechnicalDay(title)} />,
    );

    assert.equal(
      html.includes(`<h3 class="sp-session-title">${title}`),
      true,
      `expected renderer to preserve ${title}`,
    );
    assert.equal(html.includes(summary), true, `expected stage summary for ${title}`);
  }
});

test("converted sparring title and summary survive when contact shares a day with app work", () => {
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
  assert.equal(
    html.includes("Light technical rounds. Prioritise timing, flow and clean execution."),
    true,
  );
});
