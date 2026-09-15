import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { applyGlossaryMarkup, brandViolations, glossaryViolations, hasResidualMarkup, stripGlossaryMarkup } from "../i18n/glossary.mjs";
import { TARGET_LOCALES } from "./i18n-catalog.mjs";
import { englishMarkers, ENGLISH_UI_PHRASES, glossaryIssues, untranslatedLiterals } from "./i18n-glossary-check.mjs";

const directory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../messages");
const read = async (locale) => JSON.parse(await readFile(path.join(directory, `${locale}.json`), "utf8"));
const source = await read("en");
const locales = Object.keys(TARGET_LOCALES);

test("known static English UI text on a non-English locale is a failure", () => {
  const english = { AppText: { a: "Not set", b: "No active plan", c: "Delete selected" } };
  const spanish = { AppText: { a: "Sin definir", b: "No active plan", c: "Delete selected" } };
  const stale = untranslatedLiterals(english, spanish, "es");
  assert.deepEqual(stale.map((entry) => entry.keyPath), ["AppText.b", "AppText.c"]);
});

test("a phrase spelled the same in a locale is not reported for that locale", () => {
  const english = { AppText: { a: "Plan" } };
  const target = { AppText: { a: "Plan" } };
  assert.deepEqual(untranslatedLiterals(english, target, "fr"), []);
  assert.equal(untranslatedLiterals(english, { AppText: { a: "Plan" } }, "pt-BR").length, 1);
});

test("every known English UI phrase is actually translated in every locale", async () => {
  for (const locale of locales) {
    const stale = untranslatedLiterals(source, await read(locale), locale);
    assert.deepEqual(
      stale.map((entry) => `${entry.keyPath}: ${entry.value}`),
      [],
      `${locale} still shows English UI copy`,
    );
  }
});

test("the phrase list only names copy the English catalog actually uses", () => {
  const values = new Set(Object.values(source.AppText).concat(
    Object.values(source).flatMap((group) => typeof group === "object" ? Object.values(group) : []),
  ).map((value) => String(value).trim().toLocaleLowerCase()));
  const unused = ENGLISH_UI_PHRASES.filter((phrase) => !values.has(phrase.trim().toLocaleLowerCase()));
  assert.deepEqual(unused, [], "these phrases no longer exist in en.json and should be dropped");
});

test("the named regressions each fail the coverage check", () => {
  // One case per class the audit asked this test to catch. Each is a value a locale could
  // plausibly ship with English still in it, and each must be reported.
  const cases = [
    ["AppText.a", "Not set", "Not set"],
    ["AppText.b", "No active plan", "No active plan"],
    ["AppText.c", "Unable to load plan.", "Unable to load plan."],
    ["AppText.d", "Unable to save draft.", "Unable to save draft."],
    ["AppText.e", "Delete selected", "Delete selected"],
    ["AppText.f", "Training day", "Training day"],
    ["AppText.g", "Rehab block", "Rehab block"],
  ];
  for (const [keyPath, english, spanish] of cases) {
    const key = keyPath.split(".")[1];
    const stale = untranslatedLiterals({ AppText: { [key]: english } }, { AppText: { [key]: spanish } }, "es");
    assert.equal(stale.length, 1, `${english} was not reported as untranslated`);
  }
});

test("English left inside an otherwise translated value is a failure", () => {
  // The exact-value check cannot see these: the value differs from the English, but the
  // English is still in it. This is how "Delete selected (3)" shipped.
  const english = {
    AppText: {
      count: "Delete selected ({count})",
      mixed: "Could not reach the server. Unable to load plan.",
      archived: "Select archived ({count})",
    },
  };
  const spanish = {
    AppText: {
      count: "Delete selected ({count})",
      mixed: "No se pudo contactar con el servidor. Unable to load plan.",
      archived: "Seleccionar archivados ({count})",
    },
  };
  const leaks = englishMarkers(english, spanish, "es");
  assert.deepEqual(leaks.map((leak) => leak.keyPath).sort(), ["AppText.count", "AppText.mixed"]);
});

test("a marker is not reported when the English source never used it", () => {
  // "selected" appears in the Spanish word "seleccionados"; the word-boundary match and the
  // requirement that the English source carry the marker both have to hold.
  const english = { AppText: { a: "Choose your training days" } };
  const spanish = { AppText: { a: "Elige tus días de entrenamiento" } };
  assert.deepEqual(englishMarkers(english, spanish, "es"), []);
});

test("intentionally English product vocabulary is never reported", () => {
  const english = {
    AppText: {
      brand: "Unable to load Quick Build",
      day: "Light Combat day",
    },
  };
  const italian = {
    AppText: {
      brand: "Impossibile caricare Quick Build",
      day: "Giorno Light Combat",
    },
  };
  assert.deepEqual(englishMarkers(english, italian, "it"), []);
});

test("no shipped locale leaks English inside a translated value", async () => {
  for (const locale of locales) {
    const leaks = englishMarkers(source, await read(locale), locale);
    assert.deepEqual(
      leaks.map((leak) => `${leak.keyPath}: kept "${leak.marker}"`),
      [],
      `${locale} still carries English inside a value`,
    );
  }
});

test("the combat-sports sense of an ambiguous term is enforced", () => {
  assert.deepEqual(
    glossaryViolations("Heavy bag rounds reduced", "Munición de sacos pesados reducida", "es"),
    [{ term: "round", rendering: "Munición" }],
  );
  assert.deepEqual(glossaryViolations("Settings", "Décors", "fr"), [{ term: "settings", rendering: "Décors" }]);
  assert.deepEqual(glossaryViolations("Reaction drills increased", "Mais exercícios de reação", "pt-BR"), []);
  assert.deepEqual(glossaryViolations("Refine intake", "Affina il questionario", "it"), []);
});

test("a term is only policed where the English string uses it", () => {
  // "combate" is the right word for the app's own "combat day", and wrong only as sparring.
  assert.deepEqual(glossaryViolations("Combat day", "Día de combate", "es"), []);
  // "información" contains "formación" and must not read as the training defect.
  assert.deepEqual(glossaryViolations("Training information", "Información de entrenamiento", "es"), []);
  // "segundo plano" is the correct Spanish for "in the background".
  assert.deepEqual(glossaryViolations("The plan runs in the background", "El plan se ejecuta en segundo plano", "es"), []);
});

test("translating a product name away is a failure", () => {
  assert.deepEqual(brandViolations("Quick Build plan", "Plan de construcción rápida"), ["Quick Build"]);
  assert.deepEqual(brandViolations("Quick Build plan", "Plan de Quick Build"), []);
  // "Lxcked in." is the one brand word a human may carry across as meaning.
  assert.deepEqual(brandViolations("Lxcked in.", "Foco total."), []);
});

test("the shipped catalogs satisfy the glossary", async () => {
  for (const locale of locales) {
    const issues = glossaryIssues(source, await read(locale), locale);
    assert.deepEqual(issues.map((issue) => `${issue.keyPath}: ${issue.detail}`), [], `${locale} breaks the glossary`);
  }
});

test("Azure is handed dictionary hints and notranslate markup", () => {
  const marked = applyGlossaryMarkup("Heavy bag rounds for your fight camp in UNLXCK", "es");
  assert.match(marked, /<mstrans:dictionary translation="Saco pesado">Heavy bag<\/mstrans:dictionary>/);
  assert.match(marked, /<mstrans:dictionary translation="rounds">rounds<\/mstrans:dictionary>/);
  assert.match(marked, /<span class="notranslate">UNLXCK<\/span>/);
  // Markup is never nested inside markup.
  assert.equal(/<mstrans:dictionary[^>]*translation="[^"]*</.test(marked), false);
});

test("markup Azure echoes back is unwrapped instead of shipped", () => {
  const echoed = '<mstrans:dictionary translation="camp">camp</mstrans:dictionary> de <span class="notranslate">UNLXCK</span>';
  assert.equal(hasResidualMarkup(echoed), true);
  assert.equal(stripGlossaryMarkup(echoed), "camp de UNLXCK");
});
