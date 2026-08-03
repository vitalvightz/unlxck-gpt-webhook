import test from "node:test";
import assert from "node:assert/strict";

import { glossaryEntry } from "./glossary";

test("RPE resolves however the label is cased or spaced", () => {
  for (const spelling of ["RPE", "rpe", " Rpe "]) {
    const entry = glossaryEntry(spelling);
    assert.ok(entry, `expected an entry for "${spelling}"`);
    assert.equal(entry.term, "RPE");
    assert.match(entry.definition, /Rate of Perceived Exertion/);
    // The scale itself is the thing the athlete cannot infer from "RPE 1.5",
    // so both ends of it have to be spelled out.
    assert.match(entry.definition, /\bfrom 1\b/);
    assert.match(entry.definition, /\bto 10\b/);
  }
});

test("multi-word labels resolve from the text the card prints", () => {
  const entry = glossaryEntry("Stop rule");
  assert.ok(entry);
  assert.equal(entry.term, "Stop rule");
});

test("plain-English labels carry no gloss, so no stray question marks render", () => {
  // These are rendered through the same GlossaryTooltip call as Volume/Mode, and
  // must stay silent — a "?" on every stat would bury the ones that matter.
  for (const plain of ["Duration", "Distance", "Rounds", "Work", "Rest", "Swaps", "Easier", "Progress", "Strength", "Conditioning"]) {
    assert.equal(glossaryEntry(plain), null, `"${plain}" should need no definition`);
  }
});

test("a missing or non-string label is not a lookup error", () => {
  assert.equal(glossaryEntry(null), null);
  assert.equal(glossaryEntry(undefined), null);
  assert.equal(glossaryEntry(""), null);
});

test("every definition stays short enough to read in a tooltip", () => {
  for (const term of ["RPE", "Load", "Volume", "Mode", "Rehab", "Prehab", "Stop rule", "Deload", "Taper", "GPP", "SPP"]) {
    const entry = glossaryEntry(term);
    assert.ok(entry, `expected an entry for "${term}"`);
    assert.ok(
      entry.definition.length <= 320,
      `"${term}" definition is ${entry.definition.length} chars — too long for a glance`,
    );
  }
});
