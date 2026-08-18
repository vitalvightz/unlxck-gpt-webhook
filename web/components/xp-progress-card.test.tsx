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
  assert.match(html, /Training streak/);
  assert.match(html, /App streak/);
});

test("progress page gives near-best training feedback and keeps app streak secondary", () => {
  const html = renderToStaticMarkup(
    <XpProgressCardView mode="page" progress={progress({
      streaks: {
        adherence: { current: 8, best: 10, lastDate: "2026-08-18" },
        login: { current: 12, best: 27, lastDate: "2026-08-18" },
      },
    })} />,
  );
  assert.match(html, /Training streak/);
  assert.match(html, /2 more to match your best/);
  assert.match(html, /App streak/);
  assert.match(html, /Best 27/);
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

test("XP notifications use colons rather than em dashes", () => {
  const feedback = readFileSync(new URL("./xp-award-feedback.tsx", import.meta.url), "utf8");

  assert.match(feedback, /XP: \$\{feedback\.label\}/);
  assert.match(feedback, /LEVEL \{feedback\.level\}: \{feedback\.title\.toUpperCase\(\)\}/);
  assert.doesNotMatch(feedback, /—/);
});

test("Progress route keeps the compact card, athlete identity and latest-three history", () => {
  const layout = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
  const page = readFileSync(new URL("../app/progress/page.tsx", import.meta.url), "utf8");
  const pageCss = readFileSync(new URL("../app/xp-progress-page.css", import.meta.url), "utf8");
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
  assert.doesNotMatch(page, /Show all|showAllAwards|hiddenAwardCount/);
  assert.doesNotMatch(pageCss, /xp-award-toggle/);
  assert.match(page, /<details className="xp-page-panel xp-explanation xp-explanation-disclosure">/);
  assert.match(page, /UNLXCK XP tracks your progress inside the app\./);
  assert.match(page, /Earn XP by completing training, check-ins and plan milestones\./);
  assert.match(page, /Your rank reflects personal progress, not your official amateur or professional status\./);
  assert.match(page, /In future, XP may also unlock discounts, rewards and opportunities through UNLXCK\./);
  assert.match(page, /Public leaderboards are not available during private beta\./);
  assert.doesNotMatch(page, /Work banked\. Level earned\./);
  assert.doesNotMatch(page, /Available XP actions/);
  assert.doesNotMatch(page, /global leaderboard/i);
});

// --- Streak panel -----------------------------------------------------------

function streakDom(html: string): HTMLElement {
  const host = document.createElement("div");
  host.innerHTML = html;
  return host;
}

function streaks(
  adherence: [number, number],
  login: [number, number],
): Pick<XpProgress, "streaks"> {
  return {
    streaks: {
      adherence: { current: adherence[0], best: adherence[1], lastDate: "2026-08-18" },
      login: { current: login[0], best: login[1], lastDate: "2026-08-18" },
    },
  };
}

function streakColumns(host: HTMLElement): HTMLElement[] {
  return [...host.querySelectorAll<HTMLElement>(".xp-streak")];
}

const streakCss = readFileSync(new URL("../app/xp-interface.css", import.meta.url), "utf8");

/** Rough rule splitter: nested at-rule preludes never match, so every rule body
    in the file is still visited individually. */
function cssRules(css: string): Array<{ selector: string; body: string }> {
  return [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((match) => ({
    selector: match[1].trim(),
    body: match[2],
  }));
}

test("Overview streak panel holds both streaks in one container with matched columns", () => {
  const host = streakDom(
    renderToStaticMarkup(<XpProgressCardView progress={progress(streaks([8, 14], [12, 27]))} />),
  );

  const panels = host.querySelectorAll(".xp-streak-panel");
  assert.equal(panels.length, 1);
  assert.equal(panels[0].getAttribute("aria-label"), "Streaks");

  const columns = streakColumns(host);
  assert.equal(columns.length, 2);
  assert.deepEqual(
    columns.map((column) => column.dataset.streak),
    ["training", "app"],
    "Training streak leads, App streak follows",
  );

  // Identical structural styling: same element, same single class, no modifier.
  const values = columns.map((column) => column.querySelector(".xp-streak-value")!);
  assert.deepEqual(
    values.map((value) => `${value.tagName}.${value.className}`),
    ["P.xp-streak-value", "P.xp-streak-value"],
  );

  assert.deepEqual(
    columns.map((column) => column.querySelector(".xp-streak-label-text")!.textContent),
    ["Training streak", "App streak"],
  );
  assert.deepEqual(
    values.map((value) => value.textContent),
    ["8", "12"],
  );
  assert.deepEqual(
    columns.map((column) => column.querySelector(".xp-streak-best")!.textContent),
    ["Best 14", "Best 27"],
  );
});

test("streak values cannot inherit a different size from the stylesheet", () => {
  const sized = cssRules(streakCss).filter(
    (rule) =>
      rule.selector.includes(".xp-streak-value") &&
      /(^|[\s;])(font-size|font-weight)\s*:/.test(rule.body),
  );

  assert.ok(sized.length > 0, "the shared streak value rule should exist");
  for (const rule of sized) {
    assert.doesNotMatch(
      rule.selector,
      /\[data-streak/,
      `"${rule.selector}" scopes streak number size or weight to one column`,
    );
  }
});

test("streak panel keeps two equal columns instead of stacking on narrow screens", () => {
  const columnRules = cssRules(streakCss).filter(
    (rule) =>
      rule.selector.split(",").some((part) => part.trim().endsWith(".xp-streak-panel")) &&
      /grid-template-columns/.test(rule.body),
  );

  assert.equal(columnRules.length, 1, "one column definition, no narrow-width override");
  assert.match(columnRules[0].body, /grid-template-columns:\s*minmax\(0, 1fr\) minmax\(0, 1fr\)/);
  // Narrow panels trim gutters rather than reflowing the two columns.
  assert.match(streakCss, /@container \(max-width: \d+px\) \{/);
});

test("Overview stays compact: current and best only, no extra streak rows", () => {
  const host = streakDom(
    renderToStaticMarkup(<XpProgressCardView progress={progress(streaks([12, 14], [27, 27]))} />),
  );

  assert.equal(host.querySelectorAll(".xp-streak-note").length, 0);
  assert.equal(host.querySelectorAll(".xp-streak-track").length, 0);
  assert.equal(host.querySelectorAll(".xp-streak-extras").length, 0);
  for (const column of streakColumns(host)) {
    assert.equal(column.children.length, 3, "label, value, best");
  }
});

test("Progress page adds near-best and matched-best context to both streaks", () => {
  const host = streakDom(
    renderToStaticMarkup(
      <XpProgressCardView mode="page" progress={progress(streaks([12, 14], [27, 27]))} />,
    ),
  );

  const [training, app] = streakColumns(host);
  assert.equal(training.querySelector(".xp-streak-value")!.textContent, "12");
  assert.equal(training.querySelector(".xp-streak-best")!.textContent, "Best 14");
  assert.equal(training.querySelector(".xp-streak-note")!.textContent, "2 more to match your best");
  assert.equal(app.querySelector(".xp-streak-best")!.textContent, "Best 27");
  assert.equal(app.querySelector(".xp-streak-note")!.textContent, "You’ve matched your best");

  // Progress toward the best is only drawn while the best is still ahead.
  const trainingTrack = training.querySelector(".xp-streak-track")!;
  assert.equal(trainingTrack.getAttribute("aria-valuenow"), "12");
  assert.equal(trainingTrack.getAttribute("aria-valuemax"), "14");
  assert.equal(app.querySelector(".xp-streak-track"), null);
});

test("zero streaks stay intentional: no encouragement copy, no 0/0 progress bar", () => {
  for (const mode of ["overview", "page"] as const) {
    const host = streakDom(
      renderToStaticMarkup(
        <XpProgressCardView mode={mode} progress={progress(streaks([0, 0], [0, 0]))} />,
      ),
    );

    assert.deepEqual(
      streakColumns(host).map((column) => column.querySelector(".xp-streak-value")!.textContent),
      ["0", "0"],
      `${mode} shows both zeroes`,
    );
    assert.deepEqual(
      streakColumns(host).map((column) => column.querySelector(".xp-streak-best")!.textContent),
      ["Best 0", "Best 0"],
      `${mode} shows both bests`,
    );
    assert.equal(host.querySelectorAll(".xp-streak-note").length, 0, `${mode} invents no message`);
    assert.equal(host.querySelectorAll(".xp-streak-track").length, 0, `${mode} draws no 0/0 bar`);
    assert.doesNotMatch(host.innerHTML, /0 more to match your best/);
  }
});

test("a streak past its stored best is never announced as a new record", () => {
  const host = streakDom(
    renderToStaticMarkup(
      <XpProgressCardView mode="page" progress={progress(streaks([15, 14], [30, 27]))} />,
    ),
  );

  assert.equal(host.querySelectorAll(".xp-streak-note").length, 0);
  assert.equal(host.querySelectorAll(".xp-streak-track").length, 0);
  const copy = host.querySelector(".xp-streak-panel")!.textContent!;
  assert.doesNotMatch(copy, /new best/i);
  assert.doesNotMatch(copy, /-\d/, "no negative distance leaks into the copy");
  // The figures are still reported exactly as the server sent them.
  assert.deepEqual(
    streakColumns(host).map((column) => [
      column.querySelector(".xp-streak-value")!.textContent,
      column.querySelector(".xp-streak-best")!.textContent,
    ]),
    [
      ["15", "Best 14"],
      ["30", "Best 27"],
    ],
  );
});

test("streak icons are decorative and never the only indication of the stat", () => {
  const host = streakDom(
    renderToStaticMarkup(
      <XpProgressCardView mode="page" progress={progress(streaks([12, 14], [27, 27]))} />,
    ),
  );

  const icons = [...host.querySelectorAll(".xp-streak-icon")];
  assert.equal(icons.length, 2);
  for (const icon of icons) {
    assert.equal(icon.getAttribute("aria-hidden"), "true");
    assert.equal(icon.getAttribute("focusable"), "false");
    assert.equal(icon.textContent, "", "icons carry no text of their own");
  }

  // Screen-reader order per column: name, value, best, supporting copy.
  for (const column of streakColumns(host)) {
    assert.equal(column.getAttribute("role"), "group");
    const labelId = column.getAttribute("aria-labelledby")!;
    const label = host.querySelector(`#${labelId}`)!;
    assert.ok(label.textContent!.trim().length > 0);
    assert.ok(column.contains(label));
    assert.deepEqual(
      [...column.children].slice(0, 3).map((child) => child.className),
      ["xp-streak-label", "xp-streak-value", "xp-streak-best"],
    );
  }
});

test("Overview and Progress streak labels do not collide on ids", () => {
  const overview = renderToStaticMarkup(
    <XpProgressCardView progress={progress(streaks([1, 2], [3, 4]))} />,
  );
  const page = renderToStaticMarkup(
    <XpProgressCardView mode="page" progress={progress(streaks([1, 2], [3, 4]))} />,
  );

  const ids = (html: string) =>
    [...streakDom(html).querySelectorAll(".xp-streak")].map((column) =>
      column.getAttribute("aria-labelledby"),
    );

  assert.deepEqual(ids(overview), ["overview-training-streak-label", "overview-app-streak-label"]);
  assert.deepEqual(ids(page), ["page-training-streak-label", "page-app-streak-label"]);
});

test("the streak redesign leaves the rest of the XP card intact", () => {
  const html = renderToStaticMarkup(
    <XpProgressCardView
      progress={progress({
        ...streaks([8, 14], [12, 27]),
        state: { totalXp: 620, lastDailyLoginDate: null, recentAwards: [] },
        opportunities: [
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
  assert.match(html, /130 XP remaining/);
  assert.match(html, /xp-progress-fill/);
  assert.match(html, /NEXT/);
  assert.match(html, /MORE XP/);
  assert.match(html, /aria-label="Open XP progress"/);

  // Hierarchy: XP total, then training streak, then app streak, then next action.
  const order = ["xp-progress-number", "xp-streak-panel", "TRAINING", "APP", "NEXT"].map((token) =>
    html.indexOf(token === "TRAINING" ? "Training streak" : token === "APP" ? "App streak" : token),
  );
  assert.deepEqual([...order].sort((a, b) => a - b), order);
});
