"use client";

import type { MouseEvent } from "react";

export function PrivateBetaNutritionLink() {
  function blockNavigation(event: MouseEvent<HTMLAnchorElement>) {
    event.preventDefault();
  }

  return (
    <a
      href="/nutrition"
      className="ghost-button role-card-disabled"
      aria-disabled="true"
      tabIndex={-1}
      onClick={blockNavigation}
    >
      Open nutrition workspace
      <span className="badge role-card-badge">🚫 Coming soon</span>
    </a>
  );
}
