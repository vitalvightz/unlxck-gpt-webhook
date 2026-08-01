"use client";

import { useId, useState } from "react";

import {
  getRiskTimeframeLabel,
  getRiskWatchText,
  getVisibleRiskWatch,
} from "@/lib/today";
import type { TodayCommandView } from "@/lib/types";

/** Compact, collapsible command context for prioritized risk signals. */
export function TodayRiskWatch({
  risks,
  hasActiveInjury = false,
}: {
  risks: TodayCommandView["risk_watch"];
  hasActiveInjury?: boolean;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const overflowId = useId();
  if (!risks.length) {
    return null;
  }
  const { visible, overflow } = getVisibleRiskWatch(risks);
  const shown = isExpanded ? risks : visible;
  return (
    <section className="today-risk-watch" aria-label="Current and recent risk signals">
      <div id={overflowId} className="today-risk-list">
        {shown.map((risk, index) => {
          const timeframe = getRiskTimeframeLabel(risk.timeframe);
          const isHistoricalPain =
            risk.category === "high_pain" &&
            (risk.timeframe === "last_session" || risk.timeframe === "recent_sessions");
          return (
            <article key={`${risk.category}-${risk.label}-${index}`} className="today-risk-item" data-tone={risk.tone}>
              <div className="today-risk-heading">
                <p className="today-risk-label">{timeframe || risk.label}</p>
                {timeframe ? <p className="today-risk-signal">{risk.label}</p> : null}
              </div>
              <div className="today-risk-body">
                <p className="today-risk-text">{getRiskWatchText(risk)}</p>
                {isHistoricalPain ? (
                  <a className="today-risk-action" href="#today-injury">
                    {hasActiveInjury
                      ? "Still present? Update your injury."
                      : "Still present? Add an injury."}
                  </a>
                ) : null}
              </div>
            </article>
          );
        })}
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
