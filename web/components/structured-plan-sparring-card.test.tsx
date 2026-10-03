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

test("hard sparring context keeps its coaching cues inside the contact card", () => {
  const day = {
    date: "2026-08-26",
    countdown_label: "D-20",
    today_card: {
      headline: "Self-Review Cues",
      coach_led_contact: "Hard sparring",
      mindset_anchor: {
        focus_cue: "Control contact and protect energy for the week.",
        reset_cue: "Breathe out on your guard after each exchange.",
        intent: "Keep freshness while doing declared sparring.",
      },
    },
    sessions: [{ session_id: "review", title: "Self-Review Cues", blocks: [] }],
  } as StructuredDay;

  const html = renderToStaticMarkup(<DaySessionContext day={day} />);
  assert.match(html, /class="cm-day-context cm-day-context-contact"/);
  assert.match(html, /class="sp-coaching"/);
  assert.match(html, /Control contact and protect energy for the week/);
});

test("a declared light-combat day shows one Technical Combat block, not two", () => {
  // Saved plans stamped the converted-sparring wording on a light-combat day
  // whose headline also reads light combat: both blocks used to render.
  const day = {
    date: "2026-10-10",
    countdown_label: "D-26",
    day_type: "rest",
    planning_day_role_keys: ["light_combat_day", "tactical_watch"],
    today_card: {
      headline: "Light Combat / Technical",
      readiness_status: "train_as_planned",
      coach_led_contact: "Technical-only combat",
    },
    sessions: [
      { session_id: "locked-d-26-tactical-watch", session_type: "skill", title: "Tactical Focus", blocks: [] },
    ],
  } as unknown as StructuredDay;

  const html = renderToStaticMarkup(<DaySessionContext day={day} />);

  assert.equal(html.split("Technical Combat").length - 1, 1);
  assert.equal(html.includes("Pads, drills, movement or other lower-intensity combat work."), true);
  // Not presented as hard sparring the planner reduced.
  assert.equal(html.includes("Low load"), false);
  assert.equal(html.includes("Technical only, no hard sparring"), false);
});

test("a light-combat session card is not repeated as a contact block", () => {
  const day = {
    date: "2026-10-03",
    countdown_label: "D-33",
    day_type: "low",
    planning_day_role_keys: ["aerobic_base_day", "light_combat_day"],
    today_card: {
      headline: "Aerobic support",
      readiness_status: "train_as_planned",
      coach_led_contact: "Light Combat / Technical",
    },
    sessions: [
      { session_type: "skill", title: "Light Combat / Technical", blocks: [] },
    ],
  } as unknown as StructuredDay;

  const html = renderToStaticMarkup(<DaySessionContext day={day} />);

  assert.equal(html.includes("Technical Combat"), false);
});

test("a converted hard-sparring day still reads as reduced technical work", () => {
  const day = {
    date: "2026-10-28",
    countdown_label: "D-8",
    day_type: "rest",
    planning_day_role_keys: ["hard_sparring_day", "tactical_watch"],
    today_card: {
      headline: "Technical-only combat",
      readiness_status: "train_as_planned",
      coach_led_contact: "Technical-only combat",
    },
    sessions: [{ session_type: "skill", title: "Tactical Focus", blocks: [] }],
  } as unknown as StructuredDay;

  const html = renderToStaticMarkup(<DaySessionContext day={day} />);

  assert.equal(html.includes("Low load"), true);
});
