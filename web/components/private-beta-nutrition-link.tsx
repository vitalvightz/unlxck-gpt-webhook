"use client";

import { useEffect } from "react";

export function PrivateBetaNutritionGate() {
  useEffect(() => {
    function blockNutritionNavigation(event: MouseEvent) {
      const target = event.target;
      if (!(target instanceof Element)) return;

      const link = target.closest<HTMLAnchorElement>('a[href="/nutrition"]');
      if (!link) return;

      event.preventDefault();
      event.stopPropagation();
    }

    document.addEventListener("click", blockNutritionNavigation, true);
    document.addEventListener("auxclick", blockNutritionNavigation, true);

    return () => {
      document.removeEventListener("click", blockNutritionNavigation, true);
      document.removeEventListener("auxclick", blockNutritionNavigation, true);
    };
  }, []);

  return (
    <style>{`
      a[href="/nutrition"] {
        pointer-events: none;
        opacity: 0.48;
        cursor: not-allowed;
      }

      a[href="/nutrition"]::after {
        content: "🚫 COMING SOON";
        display: inline-flex;
        margin-left: 0.65rem;
        align-items: center;
        border: 1px solid rgba(181, 18, 43, 0.22);
        border-radius: 999px;
        padding: 0.2rem 0.55rem;
        background: rgba(181, 18, 43, 0.14);
        color: #ffd5db;
        font-family: "IBM Plex Mono", monospace;
        font-size: 0.68rem;
        letter-spacing: 0.08em;
        white-space: nowrap;
      }
    `}</style>
  );
}
