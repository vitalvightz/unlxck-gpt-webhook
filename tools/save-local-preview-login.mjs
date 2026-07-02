import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const requireFromWeb = createRequire(new URL("../web/package.json", import.meta.url));
const { chromium } = requireFromWeb("@playwright/test");

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..");
const loginEnvPath = path.join(__dirname, "local-preview-login.env");
const authStatePath = path.join(__dirname, "local-preview-auth-state.json");
const screenshotPath = path.join(repoRoot, "output", "playwright", "local-preview-login.png");

function readEnv(filePath) {
  const values = {};
  const lines = fs.readFileSync(filePath, "utf8").split(/\r?\n/);

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }

    const separatorIndex = trimmed.indexOf("=");
    if (separatorIndex === -1) {
      continue;
    }

    const key = trimmed.slice(0, separatorIndex).trim();
    let value = trimmed.slice(separatorIndex + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    values[key] = value;
  }

  return values;
}

async function main() {
  if (!fs.existsSync(loginEnvPath)) {
    throw new Error(`Missing local login env file: ${loginEnvPath}`);
  }

  const credentials = readEnv(loginEnvPath);
  const email = credentials.UNLXCK_PREVIEW_EMAIL;
  const password = credentials.UNLXCK_PREVIEW_PASSWORD;

  if (!email || !password) {
    throw new Error("UNLXCK_PREVIEW_EMAIL and UNLXCK_PREVIEW_PASSWORD must be set.");
  }

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();

  await page.goto("http://localhost:3000/login", { waitUntil: "networkidle", timeout: 30_000 });
  await page.locator("input#email").fill(email);
  await page.locator("input#password").fill(password);
  await page.getByRole("button", { name: "Log in" }).click();
  await page.waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 45_000 });
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => {});

  fs.mkdirSync(path.dirname(screenshotPath), { recursive: true });
  await page.screenshot({ path: screenshotPath, fullPage: true });
  await context.storageState({ path: authStatePath });

  const currentUrl = page.url();
  await browser.close();

  console.log(`Saved local preview auth state for ${email}`);
  console.log(`Current URL: ${currentUrl}`);
  console.log(`Auth state: ${authStatePath}`);
  console.log(`Screenshot: ${screenshotPath}`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
