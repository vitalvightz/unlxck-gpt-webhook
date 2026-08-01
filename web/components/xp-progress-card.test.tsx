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
  assert.match(html, /Level 6/);
  assert.match(html, /Contender/);
  assert.match(html, /1,240/);
  assert.match(html, /60 XP to Level 7/);
  assert.match(html, /DAILY LOGIN/);
  assert.match(html, /\+10 XP/);
  assert.match(html, /earned today/);
  assert.match(html, /RECENT/);
  assert.match(html, /Training logged/);
  assert.match(html, /Daily login/);
  assert.doesNotMatch(html, /Full training week completed/);
  assert.match(html, /role="progressbar"/);
  assert.match(html, /aria-valuemin="0"/);
  assert.match(html, /aria-valuemax="300"/);
  assert.match(html, /aria-valuenow="240"/);
});

test("fresh XP card has a neutral recent state and no session or currency content", () => {
  const html = renderToStaticMarkup(
    <XpProgressCardView state={createFreshXpState()} dailyRewardStatus="pending" />,
  );

  assert.match(html, /Level 1/);
  assert.match(html, /Rookie/);
  assert.match(html, />0</);
  assert.match(html, /No XP earned yet/);
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

  assert.match(html, /Level 8/);
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
    assert.match(container.querySelector(".xp-progress-total")?.textContent ?? "", /10 XP/);
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
  assert.match(xpBlock, /\.xp-progress-daily-value\[data-new-reward="true"\]/);
  assert.match(xpBlock, /animation:\s*none/);
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
