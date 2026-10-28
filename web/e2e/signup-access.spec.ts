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

  // Apply for beta offers Gmail, the device's mail app, or the address to copy.
  await page.getByRole("button", { name: "Apply for beta" }).click();
  await expect(page.getByRole("link", { name: "Use my email app" })).toHaveAttribute(
    "href",
    /^mailto:support@unlxck\.com\?subject=UNLXCK%20beta%20application/,
  );
  await expect(page.getByRole("link", { name: "Open in Gmail" })).toHaveAttribute(
    "href",
    /^https:\/\/mail\.google\.com\/mail\/\?view=cm&fs=1&to=support%40unlxck\.com&su=UNLXCK%20beta%20application/,
  );
  await expect(page.getByText("support@unlxck.com", { exact: true })).toBeVisible();

  // A full code submits itself; a wrong one is rejected and cleared.
  await code.fill("12345");
  await expect(page.getByText("That code isn't right")).toBeVisible();
  await expect(code).toHaveValue("");
  await expect(page.getByRole("button", { name: "Continue with Google" })).toHaveCount(0);

  await code.fill("63839");
  await expect(page.getByRole("heading", { name: "You're in." })).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue with Google", exact: true })).toBeVisible();

  // The unlock is remembered on this device, straight to the form.
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByRole("button", { name: "Continue with Google", exact: true })).toBeVisible();
});
