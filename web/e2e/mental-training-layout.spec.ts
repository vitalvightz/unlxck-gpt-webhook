import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
const markup = execFileSync(process.execPath, ["--import", "tsx", "--import", "./test/register-css-stub.mjs",
  "test/render-mental-training.mjs"], { encoding: "utf8" });
const css = readFileSync("app/globals.css", "utf8");
for (const width of [375, 1280]) {
  test(`mental tasks keep contact visible and details accessible at ${width}px`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.setViewportSize({ width, height: 850 });
    await page.setContent(`<html lang="en" data-theme="dark"><head><title>Mental training QA</title></head><body><main style="max-width:800px;margin:auto;padding:16px"><h1>Training</h1>${markup}</main></body></html>`);
    await page.addStyleTag({ content: css });
    await expect(page).toHaveTitle("Mental training QA");
    await expect(page.getByText("Hard sparring", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Visualise · 5 min" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Analyse · 7 min" })).toBeVisible();
    const task = page.locator('[data-mental-category="visualise"]');
    await expect(task.locator("details")).not.toHaveAttribute("open");
    await expect(task.getByText("Enter behind your jab, cut off the exit and reset calmly.", { exact: true })).not.toBeVisible();
    await task.locator("summary").click();
    await expect(task.locator("details")).toHaveAttribute("open");
    await expect(task.getByText("Enter behind your jab, cut off the exit and reset calmly.", { exact: true })).toBeVisible();
    await task.locator("summary").focus();
    await page.keyboard.press("Enter");
    await expect(task.locator("details")).not.toHaveAttribute("open");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    if (process.env.MENTAL_QA_SCREENSHOTS) await page.screenshot({ path: `${process.env.MENTAL_QA_SCREENSHOTS}/mental-${width}.png`, fullPage: true });
  });
}
