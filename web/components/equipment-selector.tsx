import { EQUIPMENT_ACCESS_GROUPS } from "@/lib/intake-options";

type EquipmentSelectorProps = {
  label?: string;
  selectedValues: string[];
  onToggle: (value: string) => void;
};

export function EquipmentSelector({
  label = "Equipment access",
  selectedValues,
  onToggle,
}: EquipmentSelectorProps) {
  return (
    <div className="equipment-selector" role="group" aria-label={label}>
      <p className="equipment-selection-summary" aria-live="polite">
        <span>Equipment available</span>
        <span aria-hidden="true">·</span>
        <strong>{selectedValues.length} selected</strong>
      </p>
      <div className="equipment-groups">
        {EQUIPMENT_ACCESS_GROUPS.map((group) => (
          <fieldset className="equipment-group" key={group.label}>
            <legend>{group.label}</legend>
            <div className="equipment-grid">
              {group.options.map((option) => {
                const checked = selectedValues.includes(option.value);
                return (
                  <label
                    key={option.value}
                    className={`equipment-tile${checked ? " equipment-tile-checked" : ""}`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => onToggle(option.value)}
                    />
                    <span>{option.label}</span>
                  </label>
                );
              })}
            </div>
          </fieldset>
        ))}
      </div>
    </div>
  );
}
