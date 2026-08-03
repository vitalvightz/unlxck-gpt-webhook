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

test("Overview card restores the compact level, rank, total and action rail", () => {
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

  assert.match(html, /xp-progress-level[^>]*>Level 2</);
  assert.match(html, /xp-progress-rank[^>]*>Prospect</);
  assert.match(html, /xp-progress-number[^>]*>620</);
  assert.match(html, /620 \/ 750 XP/);
  assert.match(html, /\+75 XP/);
  assert.match(html, /Complete today&#x27;s session/);
  assert.match(html, /\+100 XP/);
  assert.match(html, /Complete this training week/);
  assert.match(html, /href="\/progress"/);
  assert.match(html, /aria-label="Open XP progress"/);
  assert.match(html, /aria-valuemax="500"/);
  assert.match(html, /aria-valuenow="370"/);
  assert.match(html, /aria-valuetext="130 XP to Level 3"/);
  assert.doesNotMatch(html, /↗|xp-progress-open/);
  assert.doesNotMatch(html, /daily reward|daily login|claimed/i);
});

test("Progress-page card uses the same hierarchy without nesting action links", () => {
  const html = renderToStaticMarkup(
    <XpProgressCardView
      mode="page"
      progress={progress({
        state: {
          totalXp: 350,
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

  assert.match(html, /xp-progress-card--page/);
  assert.match(html, /xp-progress-number[^>]*>350</);
  assert.match(html, /350 \/ 750 XP/);
  assert.match(html, /href="\/today"/);
  assert.match(html, /xp-progress-action-link/);
  assert.doesNotMatch(html, /aria-label="Open XP progress"/);
});

test("Overview card displays all three server-supplied opportunities compactly", () => {
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

  assert.equal(html.match(/xp-progress-action-row/g)?.length, 3);
  assert.match(html, /First/);
  assert.match(html, /Second/);
  assert.match(html, /Third/);
});

test("Overview card has a calm empty Next state", () => {
  const html = renderToStaticMarkup(
    <XpProgressCardView progress={progress()} />,
  );

  assert.match(html, /Level 1/);
  assert.match(html, /Rookie/);
  assert.match(html, /xp-progress-number[^>]*>0</);
  assert.match(html, /0 \/ 250 XP/);
  assert.match(html, /No XP action is due right now/);
  assert.match(html, /No other action is due/);
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

  assert.match(html, /Level 8/);
  assert.match(html, /Champion/);
  assert.match(html, /10,400/);
  assert.doesNotMatch(html, /10,400 \/ /);
  assert.match(html, /aria-valuetext="Maximum level reached"/);
});

test("restored Overview card CSS disables progress motion when requested", () => {
  const css = readFileSync(new URL("../app/xp-overview-card.css", import.meta.url), "utf8");
  const reducedMotion = css.match(/@media \(prefers-reduced-motion: reduce\) \{[\s\S]*?\n\}/)?.[0] ?? "";

  assert.match(reducedMotion, /\.xp-progress-fill/);
  assert.match(reducedMotion, /transition:\s*none/);
  assert.doesNotMatch(css, /xp-progress-open/);
});

test("Progress route keeps the compact card, athlete identity and latest-three history", () => {
  const layout = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
  const page = readFileSync(new URL("../app/progress/page.tsx", import.meta.url), "utf8");
  const card = readFileSync(new URL("./xp-progress-card.tsx", import.meta.url), "utf8");

  assert.match(layout, /<XpAwardFeedback \/>/);
  assert.match(layout, /xp-interface\.css/);
  assert.match(layout, /xp-overview-card\.css/);
  assert.match(layout, /xp-progress-page\.css/);
  assert.match(card, /<Link href="\/progress"/);
  assert.match(page, /<XpProgressCardView progress=\{xp\.progress\} mode="page" \/>/);
  assert.match(page, /profile\.full_name/);
  assert.match(page, /profile\.technical_style/);
  assert.match(page, /profile\.tactical_style/);
  assert.match(page, /profile\.stance/);
  assert.match(page, /recentAwards\.slice\(0, 3\)/);
  assert.match(page, /Latest 3/);
  assert.doesNotMatch(page, /Show all/);
  assert.doesNotMatch(page, /showAllAwards/);
  assert.match(page, /<details className="xp-page-panel xp-explanation xp-explanation-disclosure">/);
  assert.match(page, /UNLXCK rank reflects your progress and completed work inside UNLXCK/);
  assert.match(page, /There is no public leaderboard during private beta/);
  assert.doesNotMatch(page, /Work banked\. Level earned\./);
  assert.doesNotMatch(page, /Available XP actions/);
  assert.doesNotMatch(page, /global leaderboard/i);
});
