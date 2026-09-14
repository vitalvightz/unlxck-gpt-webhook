import path from "node:path";
import { fileURLToPath } from "node:url";

import { syncCatalogs } from "./i18n-catalog.mjs";

const messagesDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../messages");

try {
  const result = await syncCatalogs({
    messagesDirectory,
    key: process.env.AZURE_TRANSLATOR_KEY,
    region: process.env.AZURE_TRANSLATOR_REGION,
    endpoint: process.env.AZURE_TRANSLATOR_ENDPOINT,
  });
  console.log(`i18n sync complete: ${result.translatedCount} string(s) translated.`);
} catch (error) {
  console.error(`i18n sync failed: ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
}
