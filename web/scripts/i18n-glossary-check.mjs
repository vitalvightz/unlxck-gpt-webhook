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
//
// The second check works two ways. ENGLISH_UI_PHRASES names copy whose translation must
// differ from the English, which catches a whole value that came through untouched.
// ENGLISH_MARKERS catches English left INSIDE an otherwise translated value — "Delete
// selected (3)", or "Unable to load plan." embedded in a longer sentence — which an
// exact-value comparison cannot see.

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
  "Unable to load plan.",
  "Unable to save draft.",
  "Unable to save plan. Please try again.",
  "Unable to load admin data.",
  "Unable to load feedback.",
  "Unable to load history.",
  "Unable to load nutrition workspace.",
  "Unable to load bodyweight log.",
  "Unable to update settings.",
  "Unable to update username.",
  "Unable to rename this plan.",
  "Unable to delete this plan.",
  "Unable to set active plan.",
  "Unable to archive this plan.",
  "Delete selected",
  "Delete archived",
  "Block",
  "Rehab block",
  "Training day",
  "Draft saved.",
  "Plan renamed.",
  "Plan archived.",
  "Injury added.",
  "Injury updated.",
  "Check-in failed.",
  "Password updated.",
  "Theme updated.",
  "New version available",
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

/**
 * Fragments that give away untranslated English wherever they appear inside a value.
 *
 * Each is a construction Spanish, Portuguese, French and Italian do not produce on their
 * own, so a hit means English survived. They are matched case-insensitively on word
 * boundaries, and only when the English source carries the same fragment — otherwise a
 * coincidence in the target language would read as a leak.
 */
export const ENGLISH_MARKERS = [
  "Unable to",
  "Failed to",
  "Not set",
  "Not provided",
  "Not recorded",
  "Not configured",
  "No active plan",
  "Delete selected",
  "Delete archived",
  "Select archived",
  "Untitled plan",
  "Training day",
  "Rehab block",
  "Please try again",
  "Try again",
  "Loading",
  "Saving",
  "selected",
  "Unknown",
  "Unavailable",
  "None logged",
  "None recorded",
];

/**
 * Values that are intentionally English on every locale, so a marker inside one is not a
 * defect: the product's own names, and the day-type labels the plan card prints in
 * English.
 */
export const INTENTIONAL_ENGLISH = [
  "UNLXCK",
  "Unlxck",
  "Lxcked",
  "Advanced Intake",
  "Quick Build",
  "Open Plan",
  "Fight Lab",
  "Light Combat",
  "GPT",
  "RPE",
  "Supabase",
  "Sentry",
  "OpenAI",
  "Today",
];

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

const escapeRegExp = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const markerPatterns = ENGLISH_MARKERS.map((marker) => ({
  marker,
  pattern: new RegExp(`(?<!\\p{L})${escapeRegExp(marker)}(?!\\p{L})`, "iu"),
}));
const intentionalPatterns = INTENTIONAL_ENGLISH.map(
  (term) => new RegExp(`(?<!\\p{L})${escapeRegExp(term)}(?!\\p{L})`, "iu"),
);

/**
 * English left standing inside a value on a non-English locale.
 *
 * Unlike untranslatedLiterals(), the whole value does not have to match: this reports
 * "Delete selected (3)" and a sentence that kept "Unable to load plan." in the middle.
 */
export function englishMarkers(source, target, locale) {
  const sourceFlat = flattenCatalog(source);
  const targetFlat = flattenCatalog(target);
  const found = [];
  for (const [keyPath, english] of Object.entries(sourceFlat)) {
    const translation = targetFlat[keyPath];
    if (typeof translation !== "string" || !translation.trim()) continue;
    if (intentionalPatterns.some((pattern) => pattern.test(translation))) continue;
    for (const { marker, pattern } of markerPatterns) {
      if (!pattern.test(english)) continue;
      if (pattern.test(translation)) {
        found.push({ keyPath, marker, value: translation, locale });
        break;
      }
    }
  }
  return found;
}
