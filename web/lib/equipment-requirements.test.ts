import assert from "node:assert/strict";
import test from "node:test";
import type { EquipmentRequirements } from "./api-schema.generated";
import { libraryEquipmentText } from "./equipment-requirements";

const requirement = (mode: "ALL" | "ANY" | "OPTIONAL" | "SINGLE" | "UNKNOWN", items: string[]): EquipmentRequirements => ({
  status: mode === "UNKNOWN" ? "unresolved" : "reviewed",
  groups: [{ mode, items: items.map(canonical_id => ({ canonical_id, quantity: null, kind: canonical_id === "partner" ? "partner" : "apparatus" })) }],
  source_value: "raw", source: "test", source_pointer: "/equipment", catalogue_id: "test:fixture", row_revision: "fixture", audit_decisions: ["test"], evidence: "Reviewed fixture",
});

test("simultaneous apparatus are visible on the result", () => {
  assert.equal(libraryEquipmentText({ equipment: ["sledgehammer/tire"], equipment_requirements: requirement("ALL", ["sledgehammer", "tire"]) }), "Requires: sledgehammer + tire");
});
test("alternatives and optional attachments have distinct labels", () => {
  assert.equal(libraryEquipmentText({ equipment: [], equipment_requirements: requirement("ANY", ["treadmill", "rower"]) }), "Use one: treadmill or rower");
  assert.equal(libraryEquipmentText({ equipment: [], equipment_requirements: requirement("OPTIONAL", ["handle_attachment"]) }), "Optional: handle attachment");
});
test("unknown never displays No equipment or invents components", () => {
  assert.equal(libraryEquipmentText({ equipment: [], equipment_requirements: requirement("UNKNOWN", []) }), "Equipment setup needs review");
  assert.equal(libraryEquipmentText({ equipment: null }), "Equipment unspecified");
});
test("reviewed correction supersedes original no-equipment value", () => {
  assert.equal(libraryEquipmentText({ equipment: [], equipment_requirements: requirement("SINGLE", ["pullup_bar"]) }), "Requires: pullup bar");
});
test("legacy API responses and explicit quantity remain compatible", () => {
  assert.equal(libraryEquipmentText({ equipment: [] }), "No equipment");
  assert.equal(libraryEquipmentText({ equipment: ["kettlebells"] }), "kettlebells");
  const reviewed = requirement("SINGLE", ["kettlebell"]);
  reviewed.groups[0].items[0].quantity = 2;
  assert.equal(libraryEquipmentText({ equipment: [], equipment_requirements: reviewed }), "Requires: kettlebell × 2");
});
