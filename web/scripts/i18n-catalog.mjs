import { createHash, randomUUID } from "node:crypto";
import { readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";

export const TARGET_LOCALES = {
  es: "es",
  "pt-BR": "pt",
  fr: "fr",
  it: "it",
};

const hash = (value) => createHash("sha256").update(value).digest("base64url").slice(0, 12);

export function flattenCatalog(value, prefix = "", result = {}) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`Expected an object at ${prefix || "<root>"}`);
  }
  for (const [key, child] of Object.entries(value)) {
    const keyPath = prefix ? `${prefix}.${key}` : key;
    if (typeof child === "string") result[keyPath] = child;
    else flattenCatalog(child, keyPath, result);
  }
  return result;
}

export function unflattenCatalog(flat) {
  const result = {};
  for (const [keyPath, value] of Object.entries(flat)) {
    const parts = keyPath.split(".");
    let cursor = result;
    for (const part of parts.slice(0, -1)) cursor = cursor[part] ??= {};
    cursor[parts.at(-1)] = value;
  }
  return result;
}

function namespacePaths(value, prefix = "", result = []) {
  for (const [key, child] of Object.entries(value)) {
    if (!child || typeof child !== "object" || Array.isArray(child)) continue;
    const keyPath = prefix ? `${prefix}.${key}` : key;
    result.push(keyPath);
    namespacePaths(child, keyPath, result);
  }
  return result;
}

export function catalogIssues(source, target, { allowMissing = false } = {}) {
  const sourceFlat = flattenCatalog(source);
  const targetFlat = flattenCatalog(target);
  const missing = Object.keys(sourceFlat).filter((key) => !(key in targetFlat));
  const extra = Object.keys(targetFlat).filter((key) => !(key in sourceFlat));
  const sourceNamespaces = namespacePaths(source);
  const targetNamespaces = namespacePaths(target);
  const missingNamespaces = sourceNamespaces.filter((key) => !targetNamespaces.includes(key));
  const extraNamespaces = targetNamespaces.filter((key) => !sourceNamespaces.includes(key));
  return {
    missing: allowMissing ? [] : missing,
    missingNamespaces: allowMissing ? [] : missingNamespaces,
    extra,
    extraNamespaces,
  };
}

export function assertCatalogComplete(source, target, locale) {
  const { missing, missingNamespaces, extra, extraNamespaces } = catalogIssues(source, target);
  if (missing.length || missingNamespaces.length || extra.length || extraNamespaces.length) {
    const details = [
      missingNamespaces.length ? `missing namespaces: ${missingNamespaces.join(", ")}` : "",
      missing.length ? `missing: ${missing.join(", ")}` : "",
      extraNamespaces.length ? `extra namespaces: ${extraNamespaces.join(", ")}` : "",
      extra.length ? `extra: ${extra.join(", ")}` : "",
    ].filter(Boolean).join("; ");
    throw new Error(`${locale} dictionary does not match English (${details})`);
  }
}

export function untranslatedKeys(source, target, localeState = {}) {
  const sourceFlat = flattenCatalog(source);
  const targetFlat = flattenCatalog(target);
  return Object.entries(sourceFlat)
    .filter(([keyPath, value]) => {
      if (targetFlat[keyPath] !== value) return false;
      const tracked = localeState[keyPath];
      return !tracked || tracked.sourceHash !== hash(value) || tracked.translationHash !== hash(value);
    })
    .map(([keyPath]) => keyPath);
}

const placeholders = (value) => [...value.matchAll(/\{[^{}]+\}/g)].map(([token]) => token).sort();

function maskPlaceholders(value) {
  const tokens = [];
  const text = value.replace(/\{[^{}]+\}/g, (token) => {
    const index = tokens.push(token) - 1;
    return `<span class="notranslate" data-unlxck-placeholder="${index}">${token}</span>`;
  });
  return {
    text,
    restore(translated) {
      return tokens.reduce((result, token, index) => result.replace(
        new RegExp(`<span\\b[^>]*data-unlxck-placeholder=["']${index}["'][^>]*>[\\s\\S]*?<\\/span>`, "gi"),
        token,
      ), translated);
    },
  };
}

function assertPlaceholders(source, translated, keyPath, locale) {
  const expected = placeholders(source);
  const received = placeholders(translated);
  if (JSON.stringify(expected) !== JSON.stringify(received)) {
    throw new Error(`Azure changed ICU placeholders for ${locale}.${keyPath}`);
  }
}

function translationWork(sourceFlat, targetFlat, localeState) {
  const work = [];
  for (const [keyPath, source] of Object.entries(sourceFlat)) {
    const current = targetFlat[keyPath];
    const tracked = localeState[keyPath];
    if (current === undefined || (!tracked && current === source)) {
      work.push({ keyPath, source });
      continue;
    }
    if (!tracked || tracked.sourceHash === hash(source)) continue;
    if (tracked.translationHash === hash(current)) work.push({ keyPath, source });
    else delete localeState[keyPath];
  }
  return work;
}

async function translateBatch({ endpoint, key, region, language, items, fetchImpl }) {
  const url = new URL("/translate", endpoint);
  url.searchParams.set("api-version", "3.0");
  url.searchParams.set("from", "en");
  url.searchParams.set("to", language);
  url.searchParams.set("textType", "html");
  const headers = {
    "Content-Type": "application/json",
    "Ocp-Apim-Subscription-Key": key,
    "X-ClientTraceId": randomUUID(),
  };
  if (region) headers["Ocp-Apim-Subscription-Region"] = region;
  const masked = items.map(({ source }) => maskPlaceholders(source));
  const response = await fetchImpl(url, {
    method: "POST",
    headers,
    body: JSON.stringify(masked.map(({ text }) => ({ Text: text }))),
  });
  if (!response.ok) {
    const detail = (await response.text()).slice(0, 500);
    const error = new Error(`Azure Translator returned ${response.status}: ${detail}`);
    if (response.status === 429) error.retryAfter = response.headers.get("retry-after");
    throw error;
  }
  const body = await response.json();
  if (!Array.isArray(body) || body.length !== items.length) {
    throw new Error("Azure Translator returned an unexpected response shape");
  }
  return body.map((entry, index) => {
    const translated = entry?.translations?.[0]?.text;
    if (typeof translated !== "string" || !translated.trim()) {
      throw new Error(`Azure Translator returned no text for ${items[index].keyPath}`);
    }
    return masked[index].restore(translated);
  });
}

const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function translateBatchWithRetry(options, sleepImpl) {
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await translateBatch(options);
    } catch (error) {
      if (attempt >= 2 || !/returned 429:/.test(error instanceof Error ? error.message : String(error))) throw error;
      const retryAfter = Number(error.retryAfter);
      await sleepImpl(Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter * 1_000 : 60_000 * (attempt + 1));
    }
  }
}

function azureBatches(items) {
  const batches = [];
  let current = [];
  let characterCount = 0;
  for (const item of items) {
    if (current.length && (current.length === 100 || characterCount + item.source.length > 45_000)) {
      batches.push(current);
      current = [];
      characterCount = 0;
    }
    current.push(item);
    characterCount += item.source.length;
  }
  if (current.length) batches.push(current);
  return batches;
}

const readJson = async (file, fallback) => {
  try {
    return JSON.parse(await readFile(file, "utf8"));
  } catch (error) {
    if (error?.code === "ENOENT") return fallback;
    throw error;
  }
};

async function stageJson(file, value, pretty = true) {
  const temporary = `${file}.${process.pid}.${randomUUID()}.tmp`;
  await writeFile(temporary, `${JSON.stringify(value, null, pretty ? 2 : 0)}\n`, "utf8");
  return { file, temporary };
}

export async function syncCatalogs({
  messagesDirectory,
  key,
  region = "",
  endpoint = "https://api.cognitive.microsofttranslator.com",
  fetchImpl = globalThis.fetch,
  charactersPerMinute = 30_000,
  sleepImpl = sleep,
} = {}) {
  if (!key) throw new Error("AZURE_TRANSLATOR_KEY is required");
  if (!messagesDirectory) throw new Error("messagesDirectory is required");

  const source = await readJson(path.join(messagesDirectory, "en.json"));
  const sourceFlat = flattenCatalog(source);
  const stateFile = path.join(messagesDirectory, ".azure-sync-state.json");
  const state = await readJson(stateFile, { version: 1, locales: {} });
  const drafts = [];
  let translatedCount = 0;
  let nextRequestAt = 0;

  for (const [locale, language] of Object.entries(TARGET_LOCALES)) {
    const file = path.join(messagesDirectory, `${locale}.json`);
    const target = await readJson(file, {});
    const issues = catalogIssues(source, target, { allowMissing: true });
    if (issues.extra.length || issues.extraNamespaces.length) {
      throw new Error(`${locale} has unexpected structure: ${[...issues.extraNamespaces, ...issues.extra].join(", ")}`);
    }
    const targetFlat = flattenCatalog(target);
    const localeState = state.locales[locale] ??= {};
    const work = translationWork(sourceFlat, targetFlat, localeState);

    for (const items of azureBatches(work)) {
      const batchCharacters = items.reduce((total, item) => total + item.source.length, 0);
      const delay = Math.max(0, nextRequestAt - Date.now());
      if (delay) await sleepImpl(delay);
      nextRequestAt = Date.now() + Math.ceil(batchCharacters * 60_000 / charactersPerMinute);
      const translations = await translateBatchWithRetry({ endpoint, key, region, language, items, fetchImpl }, sleepImpl);
      translations.forEach((translated, index) => {
        const item = items[index];
        assertPlaceholders(item.source, translated, item.keyPath, locale);
        targetFlat[item.keyPath] = translated;
        localeState[item.keyPath] = {
          sourceHash: hash(item.source),
          translationHash: hash(translated),
        };
      });
      translatedCount += items.length;
    }

    const completeTarget = unflattenCatalog(targetFlat);
    assertCatalogComplete(source, completeTarget, locale);
    drafts.push({ file, value: completeTarget });
  }

  const staged = [];
  for (const draft of drafts) staged.push(await stageJson(draft.file, draft.value));
  staged.push(await stageJson(stateFile, state, false));
  for (const item of staged) await rename(item.temporary, item.file);
  return { translatedCount };
}
