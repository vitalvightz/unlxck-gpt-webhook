import test from "node:test";
import assert from "node:assert/strict";

import { messages } from "@/i18n/messages";

// Public landing (logged-out homepage) copy guards. The copy itself lives in
// the `PublicHome` message namespace; these tests hold the positioning and the
// safety rules (see also lib/safety-copy.ts) against the English source:
// - Unlxck is a flexible combat-sports training platform, not camps only.
// - No medical overpromise: never imply diagnosis, injury prevention, medical
//   clearance, or guaranteed performance.
const copy = messages.en.PublicHome;

test("the hero lead names camps, ongoing training and custom plans", () => {
  const lead = copy.lead.toLowerCase();
  assert.ok(lead.includes("without a fight"), "hero lead should cover training with no fight booked");
  assert.ok(lead.includes("fight camps"), "hero lead should name fight camps");
  assert.ok(lead.includes("ongoing training"), "hero lead should name ongoing training");
  assert.ok(lead.includes("custom plans"), "hero lead should name custom plans");
});

test("the headline is no longer fight-camp only", () => {
  assert.ok(!copy.heroTitle.toLowerCase().includes("fight camp"));
  assert.equal(copy.heroTitle, `${copy.heroLine1} ${copy.heroLine2}`);
});

test("the product preview shows a concrete adapted session with a reason", () => {
  assert.ok(copy.tagReduced.length > 0, "preview should show a reduced block");
  assert.ok(copy.tagAdded.length > 0, "preview should show an added block");
  assert.ok(copy.reasonText.length > 0, "preview should give a reason");
  assert.ok(copy.example.length > 0, "preview must be labelled as an example");
});

test("the flexibility section covers the six ways the app supports training", () => {
  const titles = [1, 2, 3, 4, 5, 6].map((index) => copy[`flex${index}Title` as keyof typeof copy]);
  assert.deepEqual(titles, [
    "Fight camps",
    "Ongoing training",
    "Custom plans",
    "Workout editing",
    "Exercise library",
    "Training log",
  ]);
  assert.ok(copy.flex2Body.toLowerCase().includes("renewable"), "ongoing training is renewable blocks");
});

test("no landing copy overpromises medical safety or guaranteed performance", () => {
  const forbidden = ["injury-free", "keeps you safe", "prevent injur", "guarantee", "diagnos"];
  for (const [key, value] of Object.entries(copy)) {
    const text = value.toLowerCase();
    for (const term of forbidden) {
      assert.ok(!text.includes(term), `PublicHome.${key} must not claim "${term}": ${value}`);
    }
  }
});

test("every locale translates the headline and the two-line split matches it", () => {
  for (const [locale, catalog] of Object.entries(messages)) {
    const home = catalog.PublicHome;
    assert.equal(home.heroTitle, `${home.heroLine1} ${home.heroLine2}`, `${locale} headline split`);
    if (locale !== "en") assert.notEqual(home.heroTitle, copy.heroTitle, `${locale} headline is untranslated`);
  }
});
