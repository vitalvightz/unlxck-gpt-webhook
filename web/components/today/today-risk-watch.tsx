"use client";

import { useId, useState } from "react";

import { getRiskWatchText, getVisibleRiskWatch } from "@/lib/today";
import type { TodayCommandView } from "@/lib/types";

/** Collapsible list of the backend's prioritized risk-watch warnings. */
export function TodayRiskWatch({ risks }: { risks: TodayCommandView["risk_watch"] }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const overflowId = useId();
  if (!risks.length) {
    return null;
  }
  const { visible, overflow } = getVisibleRiskWatch(risks);
  const shown = isExpanded ? risks : visible;
  return (
    <section className="today-risk-watch" aria-label="Risk watch">
      <div id={overflowId} className="today-risk-list">
        {shown.map((risk, index) => (
          <article key={`${risk.category}-${risk.label}-${index}`} className="today-risk-item" data-tone={risk.tone}>
            <span className="today-risk-icon" aria-hidden="true">
              !
            </span>
            <div className="today-risk-copy">
              <p className="today-risk-label">{risk.label}</p>
              <p className="today-risk-text">{getRiskWatchText(risk)}</p>
            </div>
          </article>
        ))}
      </div>
      {overflow > 0 ? (
        <button
          type="button"
          className="today-risk-more"
          aria-controls={overflowId}
          aria-expanded={isExpanded}
          data-expanded={isExpanded ? "true" : "false"}
          onClick={() => setIsExpanded((current) => !current)}
        >
          {isExpanded ? "Show less" : `+${overflow} more warning${overflow > 1 ? "s" : ""}`}
        </button>
      ) : null}
    </section>
  );
}
