import assert from "node:assert/strict";
import test from "node:test";

import { LOCALE_OPTIONS, resolveLocale, SUPPORTED_LOCALES } from "@/i18n/config";
import { messages } from "@/i18n/messages";

test("each advertised locale has a local dictionary and unsupported values fall back", () => {
  assert.deepEqual(LOCALE_OPTIONS.map((option) => option.code), [...SUPPORTED_LOCALES]);
  assert.equal(resolveLocale("it"), "it");
  assert.equal(resolveLocale("unsupported"), "en");
  assert.equal(messages.it.PublicHome.heroTitle, "Il tuo camp. Bloccato dentro.");
});
