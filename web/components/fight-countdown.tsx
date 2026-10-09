"use client";

import { getFightCountdown } from "@/lib/fight-countdown";
import { formatPlanFightDate } from "@/lib/plan-format";
import type { StructuredPlan } from "@/lib/types";

/**
 * Fight-camp countdown shared by Overview (card) and Today (compact): days to
 * fight night, a gold camp-progress bar with the current week and phase, and
 * the next phase change. Renders nothing without a fight date (open plans) or
 * after fight day, so callers can drop it in unconditionally.
 */
export function FightCountdown({
  fightDate,
  trainingDay,
  phase,
  plan,
  variant = "today",
}: {
  fightDate: string | null | undefined;
  trainingDay: string | null | undefined;
  phase?: string | null;
  plan?: StructuredPlan | null;
  variant?: "today" | "overview";
}) {
  const countdown = getFightCountdown({ fightDate, trainingDay, phase, plan });
  if (!countdown) {
    return null;
  }

  const { daysOut, fightDateISO, pct, weekLabel, phaseLabel, nextLabel } = countdown;
  const fightDay = daysOut === 0;
  const meta = [weekLabel, phaseLabel].filter(Boolean).join(" · ");
  const label = fightDay ? "Fight day" : `${daysOut} ${daysOut === 1 ? "day" : "days"} to fight night`;

  return (
    <section className="fight-countdown" data-variant={variant} aria-label={`Fight countdown: ${label}`}>
      <div className="fight-countdown-head">
        <div>
          {variant === "overview" ? <p className="fight-countdown-kicker">Fight camp</p> : null}
          <p className="fight-countdown-days">
            {fightDay ? (
              "Fight day"
            ) : (
              <>
                <span className="fight-countdown-number">{daysOut}</span>{" "}
                {daysOut === 1 ? "day" : "days"} to fight night
              </>
            )}
          </p>
          {variant === "overview" ? (
            <p className="fight-countdown-date">{formatPlanFightDate(fightDateISO)}</p>
          ) : null}
        </div>
        {meta ? <span className="fight-countdown-meta">{meta}</span> : null}
      </div>
      {pct !== null ? (
        <div
          className="overview-progress-track fight-countdown-track"
          role="progressbar"
          aria-valuenow={Math.round(pct)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Camp progress"
        >
          <span className="overview-progress-fill" style={{ width: `${pct}%` }} />
        </div>
      ) : null}
      {nextLabel ? (
        <p className="fight-countdown-next">
          <span className="fight-countdown-next-label">Next</span> {nextLabel}
        </p>
      ) : null}
    </section>
  );
}
