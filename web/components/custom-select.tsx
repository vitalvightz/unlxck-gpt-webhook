"use client";

import {
  useEffect,
  useId,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
} from "react";
import { createPortal } from "react-dom";

import type { IntakeOption } from "@/lib/intake-options";

type CustomSelectProps = {
  id: string;
  value: string;
  options: IntakeOption[];
  placeholder: string;
  onChange: (value: string) => void;
  includeEmptyOption?: boolean;
  disabled?: boolean;
  invalid?: boolean;
  describedBy?: string;
};

const MENU_OFFSET = 8;
const SHEET_MEDIA_QUERY = "(max-width: 720px)";

export function CustomSelect({
  id,
  value,
  options,
  placeholder,
  onChange,
  includeEmptyOption = false,
  disabled = false,
  invalid = false,
  describedBy,
}: CustomSelectProps) {
  const menuId = `${useId().replace(/:/g, "")}-listbox`;
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [menuStyle, setMenuStyle] = useState<CSSProperties>({});
  const [isSheetMode, setIsSheetMode] = useState(false);

  const optionList: IntakeOption[] = includeEmptyOption
    ? [{ label: placeholder, value: "" }, ...options]
    : options;
  const selectedIndex = optionList.findIndex((option) => option.value === value);
  const selectedLabel = options.find((option) => option.value === value)?.label ?? value;
  const triggerLabel = selectedLabel || placeholder;

  const enabledIndices = optionList
    .map((option, index) => (!option.disabled ? index : -1))
    .filter((index) => index >= 0);

  function nearestEnabledIndex(preferredIndex: number): number {
    if (!enabledIndices.length) return -1;
    if (enabledIndices.includes(preferredIndex)) return preferredIndex;
    return enabledIndices.find((index) => index > preferredIndex) ?? enabledIndices[0];
  }

  function moveEnabled(current: number, direction: 1 | -1): number {
    if (!enabledIndices.length) return -1;
    const position = enabledIndices.indexOf(current);
    if (position < 0) return direction === 1 ? enabledIndices[0] : enabledIndices[enabledIndices.length - 1];
    return enabledIndices[(position + direction + enabledIndices.length) % enabledIndices.length];
  }

  function updateMenuPosition() {
    if (isSheetMode) {
      setMenuStyle({});
      return;
    }
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setMenuStyle({ left: rect.left, top: rect.bottom + MENU_OFFSET, width: rect.width });
  }

  function closeMenu(restoreFocus = false) {
    setIsOpen(false);
    if (restoreFocus) requestAnimationFrame(() => triggerRef.current?.focus());
  }

  function openMenu(preferredIndex = selectedIndex >= 0 ? selectedIndex : 0) {
    if (disabled) return;
    updateMenuPosition();
    setActiveIndex(nearestEnabledIndex(preferredIndex));
    setIsOpen(true);
  }

  function selectOption(option: IntakeOption) {
    if (option.disabled) return;
    onChange(option.value);
    closeMenu(true);
  }

  function handleTriggerKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (disabled) return;
    if (["Enter", " ", "ArrowDown"].includes(event.key)) {
      event.preventDefault();
      openMenu();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      openMenu(enabledIndices[enabledIndices.length - 1] ?? 0);
    }
  }

  function handleOptionKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number, option: IntakeOption) {
    if (option.disabled) {
      event.preventDefault();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex(moveEnabled(index, 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex(moveEnabled(index, -1));
    } else if (event.key === "Home") {
      event.preventDefault();
      setActiveIndex(enabledIndices[0] ?? -1);
    } else if (event.key === "End") {
      event.preventDefault();
      setActiveIndex(enabledIndices[enabledIndices.length - 1] ?? -1);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectOption(option);
    } else if (event.key === "Escape") {
      event.preventDefault();
      closeMenu(true);
    } else if (event.key === "Tab") {
      closeMenu();
    }
  }

  useEffect(() => {
    const mediaQuery = window.matchMedia(SHEET_MEDIA_QUERY);
    const sync = () => setIsSheetMode(mediaQuery.matches);
    sync();
    mediaQuery.addEventListener("change", sync);
    return () => mediaQuery.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    updateMenuPosition();
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (!target || triggerRef.current?.contains(target) || menuRef.current?.contains(target)) return;
      closeMenu();
    };
    const handleViewport = () => updateMenuPosition();
    window.addEventListener("pointerdown", handlePointerDown, true);
    window.addEventListener("resize", handleViewport);
    window.addEventListener("scroll", handleViewport, true);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown, true);
      window.removeEventListener("resize", handleViewport);
      window.removeEventListener("scroll", handleViewport, true);
    };
  }, [isOpen, isSheetMode]);

  useEffect(() => {
    if (isOpen && activeIndex >= 0) optionRefs.current[activeIndex]?.focus({ preventScroll: true });
  }, [activeIndex, isOpen]);

  return (
    <>
      <button
        ref={triggerRef}
        id={id}
        type="button"
        role="combobox"
        className={`custom-select-trigger ${!value ? "custom-select-trigger-placeholder" : ""}`.trim()}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={menuId}
        aria-invalid={invalid ? true : undefined}
        aria-describedby={describedBy}
        disabled={disabled}
        onClick={() => (isOpen ? closeMenu() : openMenu())}
        onKeyDown={handleTriggerKeyDown}
      >
        <span className="custom-select-trigger-label">{triggerLabel}</span>
        <span className="custom-select-chevron" aria-hidden="true" />
      </button>

      {isOpen
        ? createPortal(
            <>
              {isSheetMode ? (
                <div className="custom-select-sheet-backdrop" data-state="open" aria-hidden="true" onClick={() => closeMenu()} />
              ) : null}
              <div
                ref={menuRef}
                className={`custom-select-menu${isSheetMode ? " custom-select-menu-sheet" : ""}`}
                data-state="open"
                style={menuStyle}
              >
                {isSheetMode ? <div className="custom-select-sheet-handle" aria-hidden="true" /> : null}
                <div className="custom-select-menu-scroll" role="listbox" id={menuId} aria-labelledby={id}>
                  {optionList.map((option, index) => {
                    const isSelected = option.value === value;
                    const isActive = index === activeIndex;
                    return (
                      <button
                        key={`${option.value || "empty"}-${index}`}
                        ref={(node) => { optionRefs.current[index] = node; }}
                        id={`${menuId}-option-${index}`}
                        type="button"
                        role="option"
                        aria-selected={isSelected}
                        aria-disabled={option.disabled || undefined}
                        disabled={option.disabled}
                        tabIndex={option.disabled ? -1 : undefined}
                        className={`custom-select-option ${isSelected ? "custom-select-option-selected" : ""} ${isActive ? "custom-select-option-active" : ""}`.trim()}
                        style={option.disabled ? { opacity: 0.48, cursor: "not-allowed" } : undefined}
                        onClick={() => selectOption(option)}
                        onKeyDown={(event) => handleOptionKeyDown(event, index, option)}
                        onMouseEnter={() => { if (!option.disabled) setActiveIndex(index); }}
                      >
                        <span className="custom-select-option-label">{option.label}</span>
                        {option.disabledLabel ? (
                          <span
                            aria-hidden="true"
                            style={{
                              marginLeft: "auto",
                              border: "1px solid rgba(220, 38, 64, 0.35)",
                              borderRadius: 999,
                              padding: "0.2rem 0.5rem",
                              color: "rgba(240, 154, 165, 0.9)",
                              fontFamily: "IBM Plex Mono, monospace",
                              fontSize: "0.68rem",
                              letterSpacing: "0.08em",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {option.disabledLabel}
                          </span>
                        ) : null}
                      </button>
                    );
                  })}
                </div>
              </div>
            </>,
            document.body,
          )
        : null}
    </>
  );
}
