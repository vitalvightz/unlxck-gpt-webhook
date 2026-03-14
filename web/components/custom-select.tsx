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
};

type MenuPhase = "closed" | "opening" | "open" | "closing";

const MENU_OFFSET = 8;
const MENU_ANIMATION_MS = 140;

export function CustomSelect({
  id,
  value,
  options,
  placeholder,
  onChange,
  includeEmptyOption = false,
  disabled = false,
}: CustomSelectProps) {
  const menuId = `${useId().replace(/:/g, "")}-listbox`;
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const closeTimerRef = useRef<number | null>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [isMounted, setIsMounted] = useState(false);
  const [menuPhase, setMenuPhase] = useState<MenuPhase>("closed");
  const [activeIndex, setActiveIndex] = useState(-1);
  const [menuStyle, setMenuStyle] = useState<CSSProperties>({});

  const optionList = includeEmptyOption
    ? [{ label: placeholder, value: "" }, ...options]
    : options;
  const selectedIndex = optionList.findIndex((option) => option.value === value);
  const selectedLabel = options.find((option) => option.value === value)?.label ?? value;
  const triggerLabel = selectedLabel || placeholder;
  const hasValue = Boolean(value);

  function clearCloseTimer() {
    if (closeTimerRef.current !== null) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }

  function updateMenuPosition() {
    if (!triggerRef.current) {
      return;
    }
    const rect = triggerRef.current.getBoundingClientRect();
    setMenuStyle({
      left: rect.left,
      top: rect.bottom + MENU_OFFSET,
      width: rect.width,
    });
  }

  function closeMenu(options?: { restoreFocus?: boolean }) {
    const restoreFocus = options?.restoreFocus ?? false;
    clearCloseTimer();
    setIsOpen(false);
    if (!isMounted) {
      if (restoreFocus) {
        triggerRef.current?.focus();
      }
      return;
    }
    setMenuPhase("closing");
    closeTimerRef.current = window.setTimeout(() => {
      setIsMounted(false);
      setMenuPhase("closed");
      closeTimerRef.current = null;
      if (restoreFocus) {
        triggerRef.current?.focus();
      }
    }, MENU_ANIMATION_MS);
  }

  function openMenu(preferredIndex?: number) {
    if (disabled) {
      return;
    }
    clearCloseTimer();
    updateMenuPosition();
    const fallbackIndex = optionList.length > 0 ? 0 : -1;
    setActiveIndex(preferredIndex ?? (selectedIndex >= 0 ? selectedIndex : fallbackIndex));
    if (!isMounted) {
      setIsMounted(true);
    }
    setIsOpen(true);
    setMenuPhase("opening");
    window.requestAnimationFrame(() => {
      setMenuPhase("open");
    });
  }

  function selectValue(nextValue: string) {
    onChange(nextValue);
    closeMenu({ restoreFocus: true });
  }

  function handleTriggerKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (disabled) {
      return;
    }

    if (["Enter", " ", "ArrowDown"].includes(event.key)) {
      event.preventDefault();
      openMenu(selectedIndex >= 0 ? selectedIndex : 0);
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      openMenu(selectedIndex >= 0 ? selectedIndex : optionList.length - 1);
    }
  }

  function handleOptionKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number, nextValue: string) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((current) => (current + 1) % optionList.length);
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) => (current - 1 + optionList.length) % optionList.length);
      return;
    }

    if (event.key === "Home") {
      event.preventDefault();
      setActiveIndex(0);
      return;
    }

    if (event.key === "End") {
      event.preventDefault();
      setActiveIndex(optionList.length - 1);
      return;
    }

    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectValue(nextValue);
      return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      closeMenu({ restoreFocus: true });
      return;
    }

    if (event.key === "Tab") {
      closeMenu();
      return;
    }

    setActiveIndex(index);
  }

  useEffect(() => {
    if (!isMounted) {
      return;
    }

    updateMenuPosition();

    function handlePointerDown(event: PointerEvent) {
      const target = event.target as Node | null;
      if (!target) {
        return;
      }
      if (triggerRef.current?.contains(target) || menuRef.current?.contains(target)) {
        return;
      }
      closeMenu();
    }

    function handleViewportChange() {
      if (!isOpen) {
        return;
      }
      updateMenuPosition();
    }

    window.addEventListener("pointerdown", handlePointerDown, true);
    window.addEventListener("resize", handleViewportChange);
    window.addEventListener("scroll", handleViewportChange, true);

    return () => {
      window.removeEventListener("pointerdown", handlePointerDown, true);
      window.removeEventListener("resize", handleViewportChange);
      window.removeEventListener("scroll", handleViewportChange, true);
    };
  }, [isMounted, isOpen]);

  useEffect(() => {
    if (!isOpen || activeIndex < 0) {
      return;
    }
    const nextTarget = optionRefs.current[activeIndex];
    if (nextTarget) {
      nextTarget.focus({ preventScroll: true });
    }
  }, [activeIndex, isOpen]);

  useEffect(() => {
    return () => {
      clearCloseTimer();
    };
  }, []);

  return (
    <>
      <button
        ref={triggerRef}
        id={id}
        type="button"
        className={`custom-select-trigger ${!hasValue ? "custom-select-trigger-placeholder" : ""}`.trim()}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={menuId}
        disabled={disabled}
        onClick={() => (isOpen ? closeMenu() : openMenu())}
        onKeyDown={handleTriggerKeyDown}
      >
        <span className="custom-select-trigger-label">{triggerLabel}</span>
        <span className="custom-select-chevron" aria-hidden="true" />
      </button>
      {isMounted
        ? createPortal(
            <div
              ref={menuRef}
              className="custom-select-menu"
              data-state={menuPhase}
              style={menuStyle}
            >
              <div className="custom-select-menu-scroll" role="listbox" id={menuId} aria-labelledby={id}>
                {optionList.map((option, index) => {
                  const isSelected = option.value === value;
                  const isActive = index === activeIndex;
                  return (
                    <button
                      key={`${option.value || "empty"}-${index}`}
                      ref={(node) => {
                        optionRefs.current[index] = node;
                      }}
                      id={`${menuId}-option-${index}`}
                      type="button"
                      role="option"
                      aria-selected={isSelected}
                      className={`custom-select-option ${isSelected ? "custom-select-option-selected" : ""} ${isActive ? "custom-select-option-active" : ""}`.trim()}
                      onClick={() => selectValue(option.value)}
                      onKeyDown={(event) => handleOptionKeyDown(event, index, option.value)}
                      onMouseEnter={() => setActiveIndex(index)}
                    >
                      <span className="custom-select-option-label">{option.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
