import { EQUIPMENT_ACCESS_GROUPS } from "@/lib/intake-options";
import { translateUiText } from "@/i18n/ui-text";
import { useTranslations as useAppTranslations } from "next-intl";


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
    const appText = useAppTranslations("AppText");
  return (
    <div className="equipment-selector" role="group" aria-label={label}>
      <p className="equipment-selection-summary" aria-live="polite">
        <span>{appText("text_8b01437676e8")}</span>
        <span aria-hidden="true">{appText("text_a137f17a19a0")}</span>
        <strong>{selectedValues.length} {appText("text_d7cbbb688b2e")}</strong>
      </p>
      <div className="equipment-groups">
        {EQUIPMENT_ACCESS_GROUPS.map((group) => (
          <fieldset className="equipment-group" key={group.label}>
            <legend>{translateUiText(appText, group.label)}</legend>
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
                    <span>{translateUiText(appText, option.label)}</span>
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
