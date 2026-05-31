import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { isolateFromNetwork } from "./support";

const BASE_URL = "http://127.0.0.1:3100";

// Beta-level accessibility safety net. We scan the most important anonymous
// routes and fail only on `serious`/`critical` violations from the stable
// WCAG 2.0/2.1 A & AA rule sets. Color-contrast is excluded because it is a
// design-system decision tracked separately, not a route-correctness bug.
const ACCESSIBILITY_ROUTES = ["/", "/login"] as const;

for (const route of ACCESSIBILITY_ROUTES) {
  test(`a11y: ${route} has no serious/critical violations`, async ({ page }) => {
    await isolateFromNetwork(page, BASE_URL);
    await page.goto(route, { waitUntil: "domcontentloaded" });

    // Basic landmark + title expectations.
    await expect(page).toHaveTitle(/.+/);
    await expect(page.locator("main")).toBeVisible();

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .disableRules(["color-contrast"])
      .analyze();

    const blocking = results.violations.filter(
      (violation) => violation.impact === "serious" || violation.impact === "critical",
    );

    const summary = blocking
      .map((violation) => `${violation.id} (${violation.impact}): ${violation.nodes.length} node(s)`)
      .join("\n");

    expect(blocking, `serious/critical a11y violations on ${route}:\n${summary}`).toEqual([]);
  });
}
