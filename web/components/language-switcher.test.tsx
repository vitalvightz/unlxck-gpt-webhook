import assert from "node:assert/strict";
import test from "node:test";

import { LOCALE_OPTIONS, profileLocaleToRestore, resolveLocale, shouldPersistLocale, SUPPORTED_LOCALES } from "@/i18n/config";
import { messages } from "@/i18n/messages";

test("each advertised locale has a local dictionary and unsupported values fall back", () => {
  assert.deepEqual(LOCALE_OPTIONS.map((option) => option.code), [...SUPPORTED_LOCALES]);
  assert.equal(resolveLocale("it"), "it");
  assert.equal(resolveLocale("unsupported"), "en");
  assert.equal(messages.it.PublicHome.heroTitle, "Il tuo camp. Focus totale.");
});

test("a signed-in profile restores locale only when the cookie is absent", () => {
  assert.equal(profileLocaleToRestore(null, "pt-BR", "en"), "pt-BR");
  assert.equal(profileLocaleToRestore("es", "pt-BR", "es"), null);
  assert.equal(profileLocaleToRestore(null, "unsupported", "en"), null);
});

test("a changed signed-in locale is persisted to the profile", () => {
  assert.equal(shouldPersistLocale("access-token", "en", "it"), true);
  assert.equal(shouldPersistLocale("access-token", "it", "it"), false);
  assert.equal(shouldPersistLocale(null, "en", "it"), false);
});
