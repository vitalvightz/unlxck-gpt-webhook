import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { assertCatalogComplete, syncCatalogs, TARGET_LOCALES, untranslatedKeys } from "./i18n-catalog.mjs";

const writeJson = (file, value) => writeFile(file, `${JSON.stringify(value, null, 2)}\n`, "utf8");

async function fixture() {
  const directory = await mkdtemp(path.join(tmpdir(), "unlxck-i18n-"));
  const source = { Navigation: { hello: "Hello", welcome: "Welcome, {name}" } };
  await writeJson(path.join(directory, "en.json"), source);
  for (const locale of Object.keys(TARGET_LOCALES)) {
    await writeJson(path.join(directory, `${locale}.json`), { Navigation: { hello: `${locale} hello` } });
  }
  return { directory, source };
}

test("sync sends only missing strings and preserves existing translations", async () => {
  const { directory, source } = await fixture();
  const requests = [];
  const fetchImpl = async (url, init) => {
    const body = JSON.parse(init.body);
    requests.push({ url: String(url), body });
    return new Response(JSON.stringify(body.map(({ Text }) => ({ translations: [{ text: Text.replace("Welcome", "Translated") }] }))), { status: 200 });
  };

  const result = await syncCatalogs({ messagesDirectory: directory, key: "test-key", fetchImpl });

  const targetLocaleCount = Object.keys(TARGET_LOCALES).length;
  assert.equal(result.translatedCount, targetLocaleCount);
  assert.equal(requests.length, targetLocaleCount);
  assert.ok(requests.every(({ body }) => body.length === 1 && body[0].Text === 'Welcome, <span class="notranslate" data-unlxck-placeholder="0">{name}</span>'));
  for (const locale of Object.keys(TARGET_LOCALES)) {
    const target = JSON.parse(await readFile(path.join(directory, `${locale}.json`), "utf8"));
    assert.equal(target.Navigation.hello, `${locale} hello`);
    assert.equal(target.Navigation.welcome, "Translated, {name}");
    assertCatalogComplete(source, target, locale);
  }
});

test("an Azure failure leaves every dictionary unchanged", async () => {
  const { directory } = await fixture();
  const before = await Promise.all(Object.keys(TARGET_LOCALES).map((locale) => readFile(path.join(directory, `${locale}.json`), "utf8")));
  let calls = 0;
  const fetchImpl = async (_url, init) => {
    calls += 1;
    if (calls === 2) return new Response("translation unavailable", { status: 503 });
    const body = JSON.parse(init.body);
    return new Response(JSON.stringify(body.map(() => ({ translations: [{ text: "Tradotto, {name}" }] }))));
  };

  await assert.rejects(syncCatalogs({ messagesDirectory: directory, key: "test-key", fetchImpl }), /503/);
  const after = await Promise.all(Object.keys(TARGET_LOCALES).map((locale) => readFile(path.join(directory, `${locale}.json`), "utf8")));
  assert.deepEqual(after, before);
});

test("a 429 response waits for Azure's retry delay and retries the batch", async () => {
  const { directory } = await fixture();
  const waits = [];
  let firstRequest = true;
  const fetchImpl = async (_url, init) => {
    if (firstRequest) {
      firstRequest = false;
      return new Response("rate limited", { status: 429, headers: { "retry-after": "2" } });
    }
    const body = JSON.parse(init.body);
    return new Response(JSON.stringify(body.map(({ Text }) => ({ translations: [{ text: Text.replace("Welcome", "Traduit") }] }))));
  };

  const result = await syncCatalogs({
    messagesDirectory: directory,
    key: "test-key",
    fetchImpl,
    sleepImpl: async (milliseconds) => waits.push(milliseconds),
  });

  assert.equal(result.translatedCount, Object.keys(TARGET_LOCALES).length);
  assert.ok(waits.includes(2_000));
});

test("structural validation reports missing namespaces and keys", () => {
  assert.throws(
    () => assertCatalogComplete({ Navigation: { hello: "Hello" }, Auth: { login: "Log in" } }, { Navigation: {} }, "es"),
    /Navigation\.hello.*Auth\.login/,
  );
});

test("untracked English source copies cannot masquerade as translated coverage", () => {
  const source = { Navigation: { hello: "Hello" } };
  assert.deepEqual(untranslatedKeys(source, source), ["Navigation.hello"]);
});

test("a human edit is preserved when its tracked English source later changes", async () => {
  const { directory } = await fixture();
  const translate = async (_url, init) => {
    const body = JSON.parse(init.body);
    return new Response(JSON.stringify(body.map(({ Text }) => ({ translations: [{ text: `AUTO: ${Text}` }] }))));
  };
  await syncCatalogs({ messagesDirectory: directory, key: "test-key", fetchImpl: translate });

  const esFile = path.join(directory, "es.json");
  const es = JSON.parse(await readFile(esFile, "utf8"));
  es.Navigation.welcome = "Human translation, {name}";
  await writeJson(esFile, es);
  const englishFile = path.join(directory, "en.json");
  const english = JSON.parse(await readFile(englishFile, "utf8"));
  english.Navigation.welcome = "A new welcome, {name}";
  await writeJson(englishFile, english);

  await syncCatalogs({ messagesDirectory: directory, key: "test-key", fetchImpl: translate });
  const after = JSON.parse(await readFile(esFile, "utf8"));
  assert.equal(after.Navigation.welcome, "Human translation, {name}");
});

test("production locale loading and switching have no Azure dependency", async () => {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const runtimeFiles = [
    "i18n/request.ts",
    "i18n/messages.ts",
    "components/language-switcher.tsx",
    "app/layout.tsx",
  ];
  for (const relativeFile of runtimeFiles) {
    const contents = await readFile(path.join(root, relativeFile), "utf8");
    assert.doesNotMatch(contents, /AZURE_TRANSLATOR|cognitive\.microsofttranslator|i18n-sync/i);
  }
});
