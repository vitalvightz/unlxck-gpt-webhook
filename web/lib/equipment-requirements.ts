import type { LibraryEntry } from "./api-schema.generated";

const readable = (value: string) => value.replaceAll("_", " ").replaceAll("-", " ");

export function libraryEquipmentText(entry: Pick<LibraryEntry, "equipment"> & Partial<Pick<LibraryEntry, "equipment_requirements">>): string {
  const requirement = entry.equipment_requirements;
  if (requirement) {
    if (requirement.status === "unresolved") return "Equipment setup needs review";
    return requirement.groups.map(group => {
      const items = group.items.map(item => `${readable(item.canonical_id)}${typeof item.quantity === "number" ? ` × ${item.quantity}` : ""}`);
      if (group.mode === "UNKNOWN") return "Equipment setup needs review";
      if (group.mode === "ANY") return `Use one: ${items.join(" or ")}`;
      if (group.mode === "OPTIONAL") return `Optional: ${items.join(" + ")}`;
      return `Requires: ${items.join(" + ")}`;
    }).join(" · ");
  }
  return entry.equipment === null ? "Equipment unspecified"
    : entry.equipment.length ? entry.equipment.map(readable).join(" · ") : "No equipment";
}
