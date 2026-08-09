import test from "node:test";
import assert from "node:assert/strict";

import { classifySessionlessDay, getCoachLedContactView } from "./structured-plan";
import type { StructuredDay } from "@/lib/types";

function technicalDay(dDay: number, headline = "Technical-only combat"): StructuredDay {
  return {
    date: "",
    countdown_label: `D-${dDay}`,
    day_type: "moderate",
    today_card: { headline, readiness_status: "train_as_planned" },
    sessions: [],
  } as StructuredDay;
}

test("legacy technical cards project the converted-sparring title from D-day", () => {
  const cases = [
    [17, "Fight-intensity technical rounds"],
    [8, "Fight-intensity technical rounds"],
    [7, "Technical rhythm only"],
    [5, "Technical rhythm only"],
    [4, "Technical touch — pads / shadow"],
    [2, "Technical touch — pads / shadow"],
    [1, "Technical activation — no contact"],
    [0, "Technical activation — no contact"],
  ] as const;

  for (const [dDay, expected] of cases) {
    const view = classifySessionlessDay(technicalDay(dDay));
    assert.equal(view.kind, "technical");
    assert.equal(view.title, expected);
  }
});

test("D-0 follows activation band while explicit countdown-specific titles are preserved", () => {
  assert.equal(
    classifySessionlessDay(technicalDay(0)).title,
    "Technical activation — no contact",
  );
  assert.equal(
    classifySessionlessDay(technicalDay(5, "Technical rhythm only")).title,
    "Technical rhythm only",
  );
});

test("legacy coach-led contact above app work uses the same D-day projection", () => {
  const day = {
    date: "",
    countdown_label: "D-5",
    day_type: "moderate",
    today_card: {
      headline: "Neural Visualization",
      readiness_status: "train_as_planned",
      coach_led_contact: "Technical-only combat",
    },
    sessions: [{ session_id: "viz", title: "Neural Visualization", blocks: [] }],
  } as StructuredDay;

  const view = getCoachLedContactView(day);
  assert.equal(view?.kind, "technical");
  assert.equal(view?.title, "Technical rhythm only");
});
