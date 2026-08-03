import "./test-dom";

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";

import { XpProgressCardView } from "./xp-progress-card";
import { createFreshXpProgress, type XpProgress } from "../lib/xp-progress";

function progress(overrides: Partial<XpProgress> = {}): XpProgress {
  const fresh = createFreshXpProgress();
  return {
    ...fresh,
    ...overrides,
    state: overrides.state ?? fresh.state,
  };
}

test("Overview card shows absolute total against the next threshold", () => {
  const html = renderToStaticMarkup(
    <XpProgressCardView
      progress={progress({
        state: {
          totalXp: 620,
          lastDailyLoginDate: null,
          recentAwards: [],
        },
        opportunities: [
          {
            code: "complete_today_session",
            label: "Complete today's session",
            xp: 75,
            href: "/today",
            priority: 30,
          },
          {
            code: "complete_training_week",
            label: "Complete this training week",
            xp: 100,
            href: "/progress",
            priority: 40,
          },
        ],
      })}
    />,
  );

  assert.match(html, /LEVEL 2/);
  assert.match(html, /PROSPECT/);
  assert.match(html, /620 \/ 750 XP/);
  assert.match(html, /\+75/);
  assert.match(html, /Complete today&#x27;s session/);
  assert.match(html, /\+100/);
  assert.match(html, /Complete this training week/);
  assert.match(html, /href="\/progress"/);
  assert.match(html, /aria-valuemax="500"/);
  assert.match(html, /aria-valuenow="370"/);
  assert.match(html, /aria-valuetext="130 XP to Level 3"/);
  assert.doesNotMatch(html, /daily reward|daily login|claimed/i);
});

test("Overview card displays at most the three opportunities supplied by the server", () => {
  const html = renderToStaticMarkup(
    <XpProgressCardView
      progress={progress({
        opportunities: [
          { code: "one", label: "First", xp: 10, href: "/today", priority: 1 },
          { code: "two", label: "Second", xp: 20, href: "/today", priority: 2 },
          { code: "three", label: "Third", xp: 30, href: "/today", priority: 3 },
        ],
      })}
    />,
  );

  assert.equal(html.match(/<li/g)?.length, 3);
  assert.match(html, /First/);
  assert.match(html, /Second/);
  assert.match(html, /Third/);
});

test("Overview card has a calm empty Next state", () => {
  const html = renderToStaticMarkup(
    <XpProgressCardView progress={progress()} />,
  );

  assert.match(html, /LEVEL 1/);
  assert.match(html, /ROOKIE/);
  assert.match(html, /0 \/ 250 XP/);
  assert.match(html, /No XP action is due right now/);
});

test("maximum level uses Champion and no invented next threshold", () => {
  const html = renderToStaticMarkup(
    <XpProgressCardView
      progress={progress({
        state: {
          totalXp: 10_400,
          lastDailyLoginDate: null,
          recentAwards: [],
        },
      })}
    />,
  );

  assert.match(html, /LEVEL 8/);
  assert.match(html, /CHAMPION/);
  assert.match(html, /10,400 XP/);
  assert.doesNotMatch(html, /10,400 \/ /);
  assert.match(html, /aria-valuetext="Maximum level reached"/);
});

test("XP interface CSS disables progress and level-up motion when requested", () => {
  const css = readFileSync(new URL("../app/xp-interface.css", import.meta.url), "utf8");
  const reducedMotion = css.match(/@media \(prefers-reduced-motion: reduce\) \{[\s\S]*?\n\}/)?.[0] ?? "";

  assert.match(reducedMotion, /\.xp-progress-fill/);
  assert.match(reducedMotion, /transition:\s*none/);
  assert.match(reducedMotion, /\.xp-level-up-feedback/);
  assert.match(reducedMotion, /animation:\s*none/);
});

test("Progress route and feedback surface are mounted app-wide", () => {
  const layout = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
  const page = readFileSync(new URL("../app/progress/page.tsx", import.meta.url), "utf8");

  assert.match(layout, /<XpAwardFeedback \/>/);
  assert.match(layout, /xp-interface\.css/);
  assert.match(page, /UNLXCK rank reflects your progress and completed work inside UNLXCK/);
  assert.match(page, /There is no public leaderboard during private beta/);
  assert.doesNotMatch(page, /global leaderboard/i);
});
