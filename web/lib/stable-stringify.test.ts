import test from "node:test";
import assert from "node:assert/strict";

import { stableStringify } from "./stable-stringify";

test("produces identical output regardless of object key order", () => {
  const a = { fight_date: "2026-07-01", athlete: { age: 28, name: "Rua" } };
  const b = { athlete: { name: "Rua", age: 28 }, fight_date: "2026-07-01" };
  assert.equal(stableStringify(a), stableStringify(b));
});

test("preserves array order, which is significant", () => {
  assert.notEqual(stableStringify([1, 2, 3]), stableStringify([3, 2, 1]));
});

test("sorts keys of objects nested inside arrays", () => {
  const a = { weeks: [{ focus: "power", index: 1 }] };
  const b = { weeks: [{ index: 1, focus: "power" }] };
  assert.equal(stableStringify(a), stableStringify(b));
});

test("handles primitives and null", () => {
  assert.equal(stableStringify(null), "null");
  assert.equal(stableStringify(42), "42");
  assert.equal(stableStringify("x"), '"x"');
});
