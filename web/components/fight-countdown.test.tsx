import "./test-dom";

import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";

import { FightCountdown } from "./fight-countdown";

test("server render shows the final day count, not the animation's start", () => {
  const html = renderToStaticMarkup(
    <FightCountdown
      fightDate="2026-06-27"
      trainingDay="2026-06-10"
      phase="SPP"
      plan={{ weeks: [{ phase_label: "SPP", start_date: "2026-06-01", end_date: "2026-06-27" }] }}
    />,
  );
  assert.match(html, /fight-countdown-number">17</);
  assert.match(html, /aria-label="Fight countdown: 17 days to fight night"/);
  assert.match(html, /fight-countdown-fill/);
});

test("renders nothing for an open plan", () => {
  assert.equal(renderToStaticMarkup(<FightCountdown fightDate={null} trainingDay="2026-06-10" />), "");
});
