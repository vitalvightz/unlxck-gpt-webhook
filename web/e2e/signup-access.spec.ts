import { expect, test } from "@playwright/test";

import { isolateFromNetwork } from "./support";

const BASE_URL = "http://127.0.0.1:3100";

test("signup asks for an access code before the account form", async ({ page, baseURL }) => {
  await isolateFromNetwork(page, baseURL ?? BASE_URL);
  await page.goto("/signup", { waitUntil: "domcontentloaded" });

  const code = page.getByLabel("Access code", { exact: true });
  await expect(page.getByRole("heading", { name: "Invite only." })).toBeVisible();
  await expect(code).toBeFocused();
  await expect(page.getByRole("button", { name: "Continue with Google" })).toHaveCount(0);

  const apply = page.getByRole("link", { name: "Apply for beta" });
  await expect(apply).toHaveAttribute("href", /^mailto:support@unlxck\.com\?subject=UNLXCK%20beta%20application/);

  await code.fill("12345");
  await page.getByRole("button", { name: "Unlock" }).click();
  await expect(page.getByText("That code isn't right")).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue with Google" })).toHaveCount(0);

  await code.fill("63839");
  await page.getByRole("button", { name: "Unlock" }).click();
  await expect(page.getByRole("button", { name: "Continue with Google", exact: true })).toBeVisible();

  // The unlock is remembered on this device.
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByRole("button", { name: "Continue with Google", exact: true })).toBeVisible();
});
