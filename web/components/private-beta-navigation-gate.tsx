"use client";

import { useEffect } from "react";

const NUTRITION_LINK_SELECTOR = 'a[href="/nutrition"]';
const INTAKE_NUTRITION_LABEL = "open nutrition workspace";

function isIntakeNutritionLink(element: Element): element is HTMLAnchorElement {
  return element instanceof HTMLAnchorElement
    && element.matches(NUTRITION_LINK_SELECTOR)
    && element.textContent?.trim().toLowerCase().includes(INTAKE_NUTRITION_LABEL) === true;
}

function gateNutritionLink(link: HTMLAnchorElement) {
  link.setAttribute("aria-disabled", "true");
  link.setAttribute("data-private-beta-disabled", "true");
  link.tabIndex = -1;
  link.title = "Nutrition workspace coming soon";
}

export function PrivateBetaNavigationGate() {
  useEffect(() => {
    const applyGate = () => {
      document.querySelectorAll(NUTRITION_LINK_SELECTOR).forEach((element) => {
        if (isIntakeNutritionLink(element)) gateNutritionLink(element);
      });
    };

    const blockNavigation = (event: Event) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const link = target.closest(NUTRITION_LINK_SELECTOR);
      if (!link || !isIntakeNutritionLink(link)) return;
      event.preventDefault();
      event.stopPropagation();
    };

    applyGate();
    const observer = new MutationObserver(applyGate);
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener("click", blockNavigation, true);
    document.addEventListener("auxclick", blockNavigation, true);

    return () => {
      observer.disconnect();
      document.removeEventListener("click", blockNavigation, true);
      document.removeEventListener("auxclick", blockNavigation, true);
    };
  }, []);

  return (
    <style>{`
      a[data-private-beta-disabled="true"] {
        pointer-events: none !important;
        opacity: 0.48 !important;
        cursor: not-allowed !important;
        display: inline-flex !important;
        align-items: center;
        gap: 0.65rem;
      }

      a[data-private-beta-disabled="true"]::after {
        content: "🚫 COMING SOON";
        display: inline-flex;
        align-items: center;
        border: 1px solid rgba(220, 38, 64, 0.35);
        border-radius: 999px;
        padding: 0.2rem 0.55rem;
        color: rgba(240, 154, 165, 0.9);
        font-family: "IBM Plex Mono", monospace;
        font-size: 0.68rem;
        letter-spacing: 0.08em;
        white-space: nowrap;
      }
    `}</style>
  );
}
