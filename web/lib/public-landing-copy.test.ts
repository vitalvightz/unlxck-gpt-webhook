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

test("the hero lead sells tracking first, with plans optional", () => {
  const lead = copy.lead.toLowerCase();
  assert.ok(lead.startsWith("track your training"), "hero lead should open on tracking, not plan generation");
  assert.ok(lead.includes("sparring"), "hero lead should name sparring");
  assert.ok(lead.includes("recovery"), "hero lead should name recovery");
  assert.ok(lead.includes("coach's programme"), "hero lead should cover following a coach's programme");
  assert.ok(lead.includes("build your own"), "hero lead should cover building your own");
  assert.ok(lead.includes("personalised plan"), "hero lead should cover a personalised plan");
});

test("the landing works alongside a coach without promising coach accounts", () => {
  for (const [key, value] of Object.entries(copy)) {
    const text = value.toLowerCase();
    for (const term of ["coach account", "team management", "manage your athletes", "roster"]) {
      assert.ok(!text.includes(term), `PublicHome.${key} must not advertise coach tooling: ${value}`);
    }
  }
});

test("the headline is no longer fight-camp only", () => {
  assert.ok(!copy.heroTitle.toLowerCase().includes("fight camp"));
  assert.equal(copy.heroTitle, `${copy.heroLine1} ${copy.heroLine2}`);
});

test("the product preview shows a concrete adapted session with a reason", () => {
  assert.ok(copy.tagReduced.length > 0, "preview should show a reduced block");
  assert.ok(copy.tagAdded.length > 0, "preview should show an added block");
  assert.ok(copy.tagUnchanged.length > 0, "preview should label the unchanged block");
  assert.ok(copy.reasonText.length > 0, "preview should give a reason");
  assert.ok(copy.example.length > 0, "preview must be labelled as an example");
});

test("the benefits section groups every capability into three benefits", () => {
  const titles = [1, 2, 3].map((index) => copy[`benefit${index}Title` as keyof typeof copy]);
  assert.deepEqual(titles, ["Build your training", "Adapt your sessions", "Track your progress"]);
  const bodies = [copy.benefit1Body, copy.benefit2Body, copy.benefit3Body].join(" ").toLowerCase();
  for (const capability of ["personalised s&c plans", "your own sessions", "check in", "recovery-based", "customise your workouts", "sparring", "library"]) {
    assert.ok(bodies.includes(capability), `benefits should still cover "${capability}"`);
  }
});

test("each benefit stays a short, scannable line", () => {
  for (const index of [1, 2, 3]) {
    const body = copy[`benefit${index}Body` as keyof typeof copy];
    assert.ok(body.length <= 80, `benefit${index}Body should fit about two lines on a phone: ${body}`);
  }
});

test("the closing CTA fits athletes who only want to track", () => {
  assert.equal(copy.finalTitle, "Your training starts here.");
});

test("every locale carries the same PublicHome keys as English", () => {
  const keys = Object.keys(copy).sort();
  for (const [locale, catalog] of Object.entries(messages)) {
    assert.deepEqual(Object.keys(catalog.PublicHome).sort(), keys, `${locale} PublicHome keys`);
  }
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
