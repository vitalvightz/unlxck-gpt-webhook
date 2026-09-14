import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { assertCatalogComplete, TARGET_LOCALES, untranslatedKeys } from "./i18n-catalog.mjs";

const directory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../messages");
const read = async (locale) => JSON.parse(await readFile(path.join(directory, `${locale}.json`), "utf8"));

try {
  const source = await read("en");
  const state = await readFile(path.join(directory, ".azure-sync-state.json"), "utf8")
    .then(JSON.parse)
    .catch((error) => error?.code === "ENOENT" ? { locales: {} } : Promise.reject(error));
  for (const locale of Object.keys(TARGET_LOCALES)) {
    const target = await read(locale);
    assertCatalogComplete(source, target, locale);
    const untranslated = untranslatedKeys(source, target, state.locales?.[locale]);
    if (untranslated.length) {
      throw new Error(`${locale} has ${untranslated.length} untranslated source copies: ${untranslated.join(", ")}`);
    }
  }
  console.log("All advertised locale dictionaries match the English structure.");
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}
