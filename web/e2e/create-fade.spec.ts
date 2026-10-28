import { expect, test } from "@playwright/test";
import { setup } from "./custom-plan-fixture";
test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: "wait" }); });

for (const [name, path] of [["Quick Build", "/quick-build"], ["Full Camp Setup", "/onboarding"], ["Build Your Own", "/plans/custom"]] as const) {
  test(`${name} opens behind the same fade through black`, async ({ page, baseURL }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await setup(page, baseURL!);
    await page.goto("/create");
    await page.evaluate(() => {
      const phases: string[] = [];
      Object.assign(window, { createFadePhases: phases });
      new MutationObserver(() => {
        const phase = document.querySelector<HTMLElement>(".fade-through")?.dataset.phase;
        if (phase) phases.push(phase);
      }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["data-phase"] });
    });
    await page.getByRole("link", { name: new RegExp(`^${name}`) }).click();
    await expect(page).toHaveURL(new RegExp(path));
    await expect(page.locator(".fade-through")).toHaveCount(0);
    const phases = await page.evaluate(() => (window as unknown as { createFadePhases: string[] }).createFadePhases);
    expect(phases).toContain("covering");
    expect(phases).toContain("covered");
  });
}
