"use client";

import Link from "next/link";
import { useMemo, type CSSProperties } from "react";

import { Skeleton } from "@/components/skeleton";
import { useXp } from "@/components/xp-provider";
import { resolveXpLevel } from "@/lib/xp";
import type { XpProgress } from "@/lib/xp-progress";

const numberFormatter = new Intl.NumberFormat("en-GB");

export type XpProgressCardViewProps = {
  progress: XpProgress;
  error?: string | null;
};

export function XpProgressCardSkeleton() {
  return (
    <article className="status-card overview-command-card xp-progress-card xp-progress-card-skeleton" aria-busy="true">
      <div className="xp-progress-heading">
        <Skeleton variant="text" width={110} height={12} />
        <Skeleton variant="text" width={90} height={16} />
      </div>
      <Skeleton variant="text" width="55%" height={42} />
      <Skeleton variant="block" width="100%" height={9} style={{ borderRadius: 999 }} />
      <div className="xp-next-skeleton">
        <Skeleton variant="text" width={48} height={11} />
        <Skeleton variant="text" width="84%" height={15} />
        <Skeleton variant="text" width="72%" height={15} />
      </div>
    </article>
  );
}

export function XpProgressCardView({ progress, error = null }: XpProgressCardViewProps) {
  const level = useMemo(() => resolveXpLevel(progress.state.totalXp), [progress.state.totalXp]);
  const ratio = level.nextLevel
    ? `${numberFormatter.format(progress.state.totalXp)} / ${numberFormatter.format(level.nextLevel.threshold)} XP`
    : `${numberFormatter.format(progress.state.totalXp)} XP`;
  const progressMaximum = level.nextLevel ? level.xpForNextLevel : 100;
  const progressNow = level.nextLevel ? level.xpWithinLevel : 100;
  const progressText = level.nextLevel
    ? `${numberFormatter.format(level.xpRemaining)} XP to Level ${level.nextLevel.level}`
    : "Maximum level reached";

  return (
    <Link href="/progress" className="xp-progress-card-link" aria-label="Open XP progress">
      <article className="status-card overview-command-card xp-progress-card">
        <div className="xp-progress-heading">
          <p className="status-label">XP PROGRESS</p>
          <span className="xp-progress-open" aria-hidden="true">↗</span>
        </div>

        <div className="xp-progress-rank-line">
          <span>LEVEL {level.currentLevel.level}</span>
          <span aria-hidden="true">—</span>
          <strong>{level.currentLevel.title.toUpperCase()}</strong>
        </div>
        <p className="xp-progress-total-ratio">{ratio}</p>

        <div
          className="xp-progress-track"
          role="progressbar"
          aria-label={level.nextLevel ? `XP progress to Level ${level.nextLevel.level}` : "Maximum XP level reached"}
          aria-valuemin={0}
          aria-valuemax={progressMaximum}
          aria-valuenow={progressNow}
          aria-valuetext={progressText}
        >
          <span
            className="xp-progress-fill"
            style={{ "--xp-progress-width": `${level.percentage}%` } as CSSProperties}
          />
        </div>

        <section className="xp-progress-next" aria-labelledby="xp-next-heading">
          <p id="xp-next-heading" className="xp-progress-section-label">NEXT</p>
          {progress.opportunities.length > 0 ? (
            <ul>
              {progress.opportunities.map((opportunity) => (
                <li key={opportunity.code}>
                  <strong>+{numberFormatter.format(opportunity.xp)}</strong>
                  <span>{opportunity.label}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="xp-progress-empty">No XP action is due right now.</p>
          )}
        </section>

        {error ? <p className="xp-progress-error">Showing your last saved XP view.</p> : null}
      </article>
    </Link>
  );
}

export function XpProgressCard() {
  const xp = useXp();
  if (!xp.isHydrated) return <XpProgressCardSkeleton />;
  return <XpProgressCardView progress={xp.progress} error={xp.error} />;
}
