import { expect, test, type Page } from "@playwright/test";

import { isolateFromNetwork } from "./support";

const BASE_URL = "http://127.0.0.1:3100";

async function chooseLanguage(page: Page, label: string) {
  const trigger = page.locator(".unlxck-language-switcher-trigger");
  await expect(async () => {
    await trigger.click();
    await expect(trigger).toHaveAttribute("aria-expanded", "true", { timeout: 1_000 });
  }).toPass({ timeout: 15_000 });
  await page.getByRole("menuitemradio", { name: label }).click();
}

for (const locale of [
  { code: "es", label: "Español", heading: "Tu camp. Totalmente enfocado.", terms: "Términos de uso", eligibility: "Elegibilidad" },
  { code: "fr", label: "Français", heading: "Ton camp. Focus total.", terms: "Conditions d’utilisation", eligibility: "Éligibilité" },
  { code: "it", label: "Italiano", heading: "Il tuo camp. Focus totale.", terms: "Termini di utilizzo", eligibility: "Ammissibilità" },
]) {
  test(`switching to ${locale.label} persists through a reload`, async ({ page, baseURL, context }) => {
    await isolateFromNetwork(page, baseURL ?? BASE_URL);
    await page.goto("/", { waitUntil: "domcontentloaded" });

    await chooseLanguage(page, locale.label);

    await expect(page.locator("html")).toHaveAttribute("lang", locale.code);
    await expect(page.getByRole("heading", { level: 1 })).toHaveAttribute("aria-label", locale.heading);
    await expect.poll(async () => (await context.cookies()).find(({ name }) => name === "unlxck_locale")?.value)
      .toBe(locale.code);

    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.locator("html")).toHaveAttribute("lang", locale.code);
    await expect(page.getByRole("heading", { level: 1 })).toHaveAttribute("aria-label", locale.heading);

    await page.goto("/legal/terms-of-use", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(locale.terms);
    await expect(page.getByRole("heading", { level: 2, name: locale.eligibility })).toBeVisible();
  });
}

test("the mobile language sheet switches to Brazilian Portuguese", async ({ page, baseURL }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await isolateFromNetwork(page, baseURL ?? BASE_URL);
  await page.goto("/", { waitUntil: "domcontentloaded" });

  await chooseLanguage(page, "Português (Brasil)");

  await expect(page.locator("html")).toHaveAttribute("lang", "pt-BR");
  await expect(page.getByRole("heading", { level: 1 })).toHaveAttribute("aria-label", "Seu camp. Foco total.");
  await page.goto("/legal/terms-of-use", { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Termos de Uso");
  await expect(page.getByRole("heading", { level: 2, name: "Elegibilidade" })).toBeVisible();
});
