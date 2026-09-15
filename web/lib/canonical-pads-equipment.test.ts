import test from "node:test";
import assert from "node:assert/strict";

import {
  EQUIPMENT_ACCESS_OPTIONS,
  canonicalizeEquipmentAccessValues,
  getOptionLabel,
  retainKnownOptionValues,
} from "@/lib/intake-options";

// Thai pads, focus mitts and partner mitts are one athlete-facing capability.
// Intake exposes it once, as "Pads / Mitts" with the canonical value `pads`,
// matching the `pads` token the backend normalizes every legacy spelling to.

test("intake exposes one combat pad option with the canonical value", () => {
  const padOptions = EQUIPMENT_ACCESS_OPTIONS.filter((option) =>
    /pad|mitt/i.test(option.label),
  );
  assert.deepEqual(padOptions, [{ label: "Pads / Mitts", value: "pads" }]);
});

test("the legacy thai_pads option is gone", () => {
  const values = EQUIPMENT_ACCESS_OPTIONS.map((option) => option.value);
  for (const legacy of ["thai_pads", "thai_pad", "focus_mitts", "partner_mitts"]) {
    assert.ok(!values.includes(legacy), `${legacy} should no longer be selectable`);
  }
});

test("legacy persisted values canonicalize to pads", () => {
  for (const legacy of ["thai_pads", "thai_pad", "focus_mitts", "partner_mitts", "mitts"]) {
    assert.deepEqual(canonicalizeEquipmentAccessValues([legacy]), ["pads"]);
  }
});

test("mixed legacy values collapse into a single pads capability", () => {
  assert.deepEqual(
    canonicalizeEquipmentAccessValues(["thai_pads", "focus_mitts", "pads"]),
    ["pads"],
  );
});

test("partner stays an independent capability alongside pads", () => {
  assert.deepEqual(canonicalizeEquipmentAccessValues(["thai_pads", "partner"]), [
    "pads",
    "partner",
  ]);
});

test("unrelated equipment is untouched", () => {
  assert.deepEqual(
    canonicalizeEquipmentAccessValues(["heavy_bag", "sled", "partner"]),
    ["heavy_bag", "sled", "partner"],
  );
});

test("a saved profile using thai_pads survives hydration instead of being dropped", () => {
  // retainKnownOptionValues drops unknown values; without canonicalization
  // first, re-saving a legacy profile would silently lose the athlete's pads.
  const hydrated = retainKnownOptionValues(
    canonicalizeEquipmentAccessValues(["thai_pads", "partner", "heavy_bag"]),
    EQUIPMENT_ACCESS_OPTIONS,
  );
  assert.deepEqual(hydrated, ["pads", "partner", "heavy_bag"]);
});

test("legacy values still render a readable label in read-only views", () => {
  assert.equal(getOptionLabel(EQUIPMENT_ACCESS_OPTIONS, "thai_pads"), "Pads / Mitts");
  assert.equal(getOptionLabel(EQUIPMENT_ACCESS_OPTIONS, "focus_mitts"), "Pads / Mitts");
  assert.equal(getOptionLabel(EQUIPMENT_ACCESS_OPTIONS, "pads"), "Pads / Mitts");
});
