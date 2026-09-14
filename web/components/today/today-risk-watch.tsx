"use client";

import { useId, useState } from "react";

import {
  getRiskTimeframeLabel,
  getRiskWatchText,
  getVisibleRiskWatch,
} from "@/lib/today";
import type { TodayCommandView } from "@/lib/types";
import { useTranslations as useAppTranslations } from "next-intl";
import { translateUiText } from "@/i18n/ui-text";

/** Compact, collapsible command context for prioritized risk signals. */
export function TodayRiskWatch({
  risks,
  hasActiveInjury = false,
}: {
  risks: TodayCommandView["risk_watch"];
  hasActiveInjury?: boolean;
}) {
    const appText = useAppTranslations("AppText");
  const [isExpanded, setIsExpanded] = useState(false);
  const overflowId = useId();
  if (!risks.length) {
    return null;
  }
  const { visible, overflow } = getVisibleRiskWatch(risks);
  const shown = isExpanded ? risks : visible;
  return (
    <section className="today-risk-watch" aria-label={appText("text_cec448e59c10")}>
      <div id={overflowId} className="today-risk-list">
        {shown.map((risk, index) => {
          const timeframe = getRiskTimeframeLabel(risk.timeframe);
          const isHistoricalPain =
            risk.category === "high_pain" &&
            (risk.timeframe === "last_session" || risk.timeframe === "recent_sessions");
          return (
              <article key={`${risk.category}-${risk.label}-${index}`} className="today-risk-item" data-tone={risk.tone}>
              <div className="today-risk-heading">
                <p className="today-risk-label">{timeframe || translateUiText(appText, risk.label)}</p>
                {timeframe ? <p className="today-risk-signal">{translateUiText(appText, risk.label)}</p> : null}
              </div>
              <div className="today-risk-body">
                <p className="today-risk-text">{translateUiText(appText, getRiskWatchText(risk))}</p>
                {isHistoricalPain ? (
                  <a className="today-risk-action" href="#today-injury">
                    {hasActiveInjury
                      ? appText("text_f898139f9933")
                      : appText("text_5c23444b0d45")}
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
          {isExpanded ? appText("text_94ea9b1d33a0") : `+${overflow} more warning${overflow > 1 ? "s" : ""}`}
        </button>
      ) : null}
    </section>
  );
}
