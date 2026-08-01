import "./test-dom";

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";

import { XpProgressCardView } from "./xp-progress-card";
import { createFreshXpState, type XpAwardRecord } from "../lib/xp";

const award = (
  id: string,
  action: XpAwardRecord["action"],
  amount: number,
): XpAwardRecord => ({
  id,
  action,
  amount,
  awardedAt: "2026-08-01T12:00:00.000Z",
});

test("XP card renders all required copy, formatted totals, recent awards, and progress ARIA", () => {
  const state = {
    ...createFreshXpState(),
    totalXp: 1_240,
    lastDailyLoginDate: "2026-08-01",
    recentAwards: [
      award("training-1", "training_logged", 25),
      award("daily-1", "daily_login", 10),
      award("week-1", "full_training_week_completed", 100),
    ],
  };
  const html = renderToStaticMarkup(
    <XpProgressCardView state={state} dailyRewardStatus="earned" />,
  );

  assert.match(html, /XP PROGRESS/);
  assert.match(html, /Contender/);
  assert.match(html, /1,240/);
  // Level and next threshold are tabular stats beside the figure, not prose.
  assert.match(html, /<dt>Level<\/dt><dd>06<\/dd>/);
  assert.match(html, /<dt>Next<\/dt><dd>1,300<\/dd>/);
  // Ledger: today's reward, the most recent other award, distance to next level.
  assert.match(html, /Today&#x27;s reward/);
  assert.match(html, /\+10 XP/);
  assert.match(html, /Training logged/);
  assert.match(html, /To Level 7/);
  assert.match(html, /60 XP/);
  assert.doesNotMatch(html, /Full training week completed/);
  assert.match(html, /role="progressbar"/);
  assert.match(html, /aria-valuemin="0"/);
  assert.match(html, /aria-valuemax="300"/);
  assert.match(html, /aria-valuenow="240"/);
  // The full sentence survives for assistive tech even though the visible
  // ledger splits it across two columns.
  assert.match(html, /aria-valuetext="60 XP to Level 7"/);
});

test("today's claimed daily login is not printed twice", () => {
  const state = {
    ...createFreshXpState(),
    totalXp: 10,
    lastDailyLoginDate: "2026-08-01",
    recentAwards: [award("daily-1", "daily_login", 10)],
  };
  const html = renderToStaticMarkup(
    <XpProgressCardView state={state} dailyRewardStatus="earned" />,
  );

  assert.match(html, /Today&#x27;s reward/);
  // The award behind "Today's reward" is dropped from the recent row rather
  // than repeated under its own label.
  assert.doesNotMatch(html, /Daily login/);
  assert.match(html, /No other XP yet/);
  assert.equal(html.match(/\+10 XP/g)?.length, 1);
});

test("an older daily login still shows once today's reward is claimed", () => {
  const state = {
    ...createFreshXpState(),
    totalXp: 45,
    lastDailyLoginDate: "2026-08-01",
    recentAwards: [
      award("daily-today", "daily_login", 10),
      award("training-1", "training_logged", 25),
    ],
  };
  const html = renderToStaticMarkup(
    <XpProgressCardView state={state} dailyRewardStatus="earned" />,
  );

  assert.match(html, /Training logged/);
  assert.equal(html.match(/Daily login/g), null);
});

test("fresh XP card has a neutral recent state and no session or currency content", () => {
  const html = renderToStaticMarkup(
    <XpProgressCardView state={createFreshXpState()} dailyRewardStatus="pending" />,
  );

  assert.match(html, /<dt>Level<\/dt><dd>01<\/dd>/);
  assert.match(html, /Rookie/);
  assert.match(html, />0</);
  assert.match(html, /No other XP yet/);
  assert.match(html, /Checking today&#x27;s reward/);
  assert.doesNotMatch(html, /Next planned session/i);
  assert.doesNotMatch(html, /upcoming workout/i);
  assert.doesNotMatch(html, /credits|coins|balance|discount|currency/i);
});

test("storage failure and maximum level states use explicit copy", () => {
  const state = { ...createFreshXpState(), totalXp: 1_700 };
  const html = renderToStaticMarkup(
    <XpProgressCardView state={state} dailyRewardStatus="unavailable" />,
  );

  assert.match(html, /<dt>Level<\/dt><dd>08<\/dd>/);
  assert.match(html, /Champion/);
  assert.match(html, /Max level reached/);
  assert.match(html, /Daily reward could not be saved/);
  assert.match(html, /aria-valuemax="100"/);
  assert.match(html, /aria-valuenow="100"/);
});

test("new daily award is identified for restrained reward motion", () => {
  const state = {
    ...createFreshXpState(),
    totalXp: 10,
    lastDailyLoginDate: "2026-08-01",
    recentAwards: [award("daily-login:2026-08-01", "daily_login", 10)],
  };
  const html = renderToStaticMarkup(
    <XpProgressCardView
      state={state}
      dailyRewardStatus="earned"
      isNewAward
      isNewDailyAward
      previousTotalXp={0}
    />,
  );
  assert.match(html, /data-new-award="true"/);
  assert.match(html, /data-new-reward="true"/);
});

test("reduced motion resolves the XP total and bar immediately", async () => {
  const previousMatchMedia = window.matchMedia;
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: (query: string) => ({
      matches: query === "(prefers-reduced-motion: reduce)",
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });

  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  const state = {
    ...createFreshXpState(),
    totalXp: 10,
    lastDailyLoginDate: "2026-08-01",
    recentAwards: [award("daily-login:2026-08-01", "daily_login", 10)],
  };

  try {
    await act(async () => {
      root.render(
        <XpProgressCardView
          state={state}
          dailyRewardStatus="earned"
          isNewAward
          isNewDailyAward
          previousTotalXp={0}
        />,
      );
    });
    // Number and unit are separate flex children with a gap, so there is no
    // whitespace text node between them; the aria-label carries the readable form.
    assert.match(container.querySelector(".xp-progress-total")?.textContent ?? "", /10\s*XP/);
    assert.equal(
      container.querySelector(".xp-progress-total")?.getAttribute("aria-label"),
      "10 experience points",
    );
    assert.equal(
      (container.querySelector(".xp-progress-fill") as HTMLElement | null)?.style.getPropertyValue("--xp-progress-width"),
      "10%",
    );
  } finally {
    await act(async () => root.unmount());
    container.remove();
    Object.defineProperty(window, "matchMedia", { configurable: true, value: previousMatchMedia });
  }
});

test("stylesheet disables every XP animation path for reduced motion", () => {
  const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
  const reducedMotionBlocks = css.match(/@media \(prefers-reduced-motion: reduce\) \{[\s\S]*?\n\}/g) ?? [];
  const xpBlock = reducedMotionBlocks.find((block) => block.includes(".xp-progress-fill"));

  assert.ok(xpBlock, "expected an XP-specific reduced-motion block");
  assert.match(xpBlock, /\.xp-progress-fill[\s\S]*transition:\s*none/);
  assert.match(xpBlock, /\.xp-progress-shimmer/);
  assert.match(xpBlock, /\.xp-progress-ledger-row\[data-new-reward="true"\]/);
  assert.match(xpBlock, /animation:\s*none/);
});

test("the XP card can fill the Overview row it sits in", () => {
  const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
  const wrapper = css.match(/\.overview-primary-session \{[\s\S]*?\n\}/)?.[0] ?? "";
  const card = css.match(/\.xp-progress-card \{[\s\S]*?\n\}/)?.[0] ?? "";

  // `align-content: start` capped the row at content height, which made any
  // height the card asked for resolve against ~72px instead of the full row.
  assert.match(wrapper, /align-content:\s*stretch/);
  assert.doesNotMatch(wrapper, /align-content:\s*start/);
  assert.match(card, /display:\s*flex/);
  assert.match(card, /flex-direction:\s*column/);
  assert.doesNotMatch(card, /min-height:\s*100%/);
  // The ledger is what anchors to the base of a stretched card.
  assert.match(css, /\.xp-progress-ledger \{[\s\S]*?margin:\s*auto 0 0/);
});

test("Overview reserves the established right-hand slot for XP without moving the left command card", () => {
  const overviewSource = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(
    overviewSource,
    /<div className="overview-primary-session">\s*<XpProgressCard \/>\s*<\/div>/,
  );
  assert.match(overviewSource, /className="status-card overview-command-card overview-decision-lead"/);
  assert.match(overviewSource, /<CampProgressBar[^>]*variant="overview"/);
  assert.doesNotMatch(overviewSource, /Next planned session/);
});

test("XP provider is app-wide and nested inside authenticated session state", () => {
  const layoutSource = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
  const providerSource = readFileSync(new URL("./xp-provider.tsx", import.meta.url), "utf8");
  assert.match(layoutSource, /<AuthProvider>\s*<XpProvider>/);
  assert.match(layoutSource, /<\/XpProvider>\s*<\/AuthProvider>/);
  assert.match(providerSource, /claimDailyLoginXp\(accessToken\)/);
  assert.doesNotMatch(providerSource, /localStorage|sessionStorage|XpPersistence/);
});
