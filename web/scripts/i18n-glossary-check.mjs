// Catalog-level enforcement of i18n/translation-context.md.
//
// Two separate failures are checked here, because the PR that machine-translated the
// app produced both:
//
//   1. a glossary defect — Azure picked the everyday sense of an ambiguous combat-sports
//      word ("rounds" as ammunition, "drill" as a power tool, "settings" as scenery), or
//      translated a product name away;
//   2. static English left standing on a non-English locale — a UI string that reached
//      the catalogs untranslated, which next-intl will happily render as English.

import { brandViolations, glossaryViolations } from "../i18n/glossary.mjs";
import { flattenCatalog } from "./i18n-catalog.mjs";

/**
 * UI copy that must never read as English on a non-English locale. These are the
 * phrases the extractor missed or that came back from Azure unchanged, plus the
 * everyday labels a reader would notice first. Domain loanwords the sport keeps in
 * every language — sparring, round, camp, UNLXCK, Advanced Intake, Quick Build — are
 * deliberately absent: those are correct as English.
 */
export const ENGLISH_UI_PHRASES = [
  "Not set",
  "Not provided",
  "Not selected",
  "Not configured",
  "Not derived yet",
  "None recorded",
  "None logged",
  "No active plan",
  "Delete selected",
  "Select",
  "Selected",
  "Settings",
  "Overview",
  "Today",
  "History",
  "Plan",
  "Log in",
  "Sign out",
  "Create account",
  "Get started",
  "Save",
  "Save changes",
  "Cancel",
  "Delete",
  "Continue",
  "Back",
  "Next",
  "Retry",
  "Loading",
  "Unavailable",
  "Athlete",
  "Coach",
  "Injury",
  "Recovery",
  "Readiness",
  "Session",
  "Training",
  "Fight date",
  "Heavy bag",
  "Focus cap",
  "Intake",
  "Intake ready",
  "Camp status",
  "Camp setup",
  "Camp day",
  "Open camp plan",
  "Untitled plan",
  "Unknown",
  "Unknown page",
  "Unknown device",
  "Unknown browser",
  "Email unavailable",
  "Authenticated user",
  "No athlete email",
  "Athlete profile",
  "Your progress",
  "Nutrition workspace",
  "Automatic",
  "Admin",
  "Days until fight",
  "Current phase",
  "Restriction level",
  "Rest",
];

/**
 * Phrases that are spelled the same in a given locale, so an identical string there is
 * a correct translation rather than a missed one.
 */
export const IDENTICAL_BY_DESIGN = {
  es: ["Plan"],
  "pt-BR": [],
  fr: ["Plan"],
  it: [],
};

const normalise = (value) => value.trim().replace(/\s+/g, " ").toLocaleLowerCase();
const phraseSet = new Set(ENGLISH_UI_PHRASES.map(normalise));
const allowedIdentical = Object.fromEntries(
  Object.entries(IDENTICAL_BY_DESIGN).map(([locale, phrases]) => [locale, new Set(phrases.map(normalise))]),
);

/** Glossary and branding defects across a whole catalog. */
export function glossaryIssues(source, target, locale) {
  const sourceFlat = flattenCatalog(source);
  const targetFlat = flattenCatalog(target);
  const issues = [];
  for (const [keyPath, english] of Object.entries(sourceFlat)) {
    const translation = targetFlat[keyPath];
    if (typeof translation !== "string") continue;
    for (const { term, rendering } of glossaryViolations(english, translation, locale)) {
      issues.push({ keyPath, detail: `"${term}" came out as "${rendering}" — see i18n/translation-context.md` });
    }
    for (const term of brandViolations(english, translation)) {
      issues.push({ keyPath, detail: `the product name "${term}" was translated away` });
    }
  }
  return issues;
}

/**
 * Keys whose English copy is known UI text that must be localised, but whose
 * translation still reads as that same English.
 */
export function untranslatedLiterals(source, target, locale) {
  const sourceFlat = flattenCatalog(source);
  const targetFlat = flattenCatalog(target);
  const stale = [];
  for (const [keyPath, english] of Object.entries(sourceFlat)) {
    if (!phraseSet.has(normalise(english))) continue;
    if (allowedIdentical[locale]?.has(normalise(english))) continue;
    const translation = targetFlat[keyPath];
    if (typeof translation !== "string") continue;
    if (normalise(translation) === normalise(english)) stale.push({ keyPath, value: translation, locale });
  }
  return stale;
}
