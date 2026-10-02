import { readFileSync } from "node:fs";
import { test, expect } from "@playwright/test";

const css = readFileSync("app/globals.css", "utf8");

for (const theme of ["dark", "light"]) {
  test(`disabled Save CTA stays subdued and still on hover and press (${theme})`, async ({ page }) => {
    await page.setContent(`<html data-theme="${theme}"><body>
      <button class="cta" disabled>Save session complete</button>
      <button class="cta">Enabled CTA</button>
    </body></html>`);
    await page.addStyleTag({ content: css });
    const save = page.getByRole("button", { name: "Save session complete" });
    const enabled = page.getByRole("button", { name: "Enabled CTA" });
    await expect(save).toBeDisabled();
    await expect(save).toHaveCSS("opacity", "0.5");
    await expect(save).toHaveCSS("cursor", "not-allowed");
    await page.evaluate(() => Promise.all(document.getAnimations().map(animation => animation.finished)));
    const background = await save.evaluate(el => getComputedStyle(el).background);
    for (const pressed of [false, true]) {
      await save.hover();
      if (pressed) await page.mouse.down();
      await expect(save).toHaveCSS("transform", "none");
      await expect(save).toHaveCSS("box-shadow", "none");
      await expect(save).toHaveCSS("background", background);
      if (pressed) await page.mouse.up();
    }
    await expect(enabled).toHaveCSS("opacity", "1");
    await expect(enabled).toHaveCSS("cursor", "pointer");
    await enabled.hover();
    await expect(enabled).toHaveCSS("transform", "matrix(1, 0, 0, 1, 0, -1)");
    await page.emulateMedia({ reducedMotion: "reduce" });
    await expect(enabled).toHaveCSS("transform", "none");
  });
}
