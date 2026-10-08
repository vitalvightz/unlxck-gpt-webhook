import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const markup = execFileSync(process.execPath, ["--import", "tsx", "--import", "./test/register-css-stub.mjs",
  "test/render-achilles-assessment.mjs"], { encoding: "utf8" });
const css = readFileSync("app/globals.css", "utf8") + readFileSync("components/today/achilles-assessment-form.module.css", "utf8");

for (const [name, width] of [["mobile", 375], ["desktop", 1280]] as const) {
  for (const theme of ["dark", "light"]) {
    test(`Achilles assessment stays usable on ${name} in ${theme} theme`, async ({ page }) => {
      await page.setViewportSize({ width, height: 850 });
      await page.setContent(`<html data-theme="${theme}" lang="en"><head><title>Assessment layout fixture</title></head><body><main style="max-width:800px;margin:auto;padding:16px"><h1>Injury check-in</h1>${markup}</main></body></html>`);
      await page.addStyleTag({ content: css });
      await page.getByText("Record Achilles assessment", { exact: true }).click();
      await expect(page.getByRole("button", { name: "Save assessment report" })).toBeVisible();
      await expect(page.getByText("It won't unlock loading rehab.", { exact: false })).toBeVisible();
      await page.getByLabel("Assessment time (your local time)").fill("2026-10-05T12:00");
      await page.getByLabel("Reported tendon site").selectOption("insertional");
      await expect(page.getByLabel("Reported tendon site")).toHaveValue("insertional");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
      await page.getByLabel("Reported tendon site").focus();
      await expect(page.getByLabel("Reported tendon site")).toBeFocused();
    });
  }
}
