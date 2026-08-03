"use client";

import Link from "next/link";
import { useMemo, type CSSProperties } from "react";

import { Skeleton } from "@/components/skeleton";
import { useXp } from "@/components/xp-provider";
import { resolveXpLevel } from "@/lib/xp";
import type { XpOpportunity, XpProgress } from "@/lib/xp-progress";

const numberFormatter = new Intl.NumberFormat("en-GB");

export type XpProgressCardViewProps = {
  progress: XpProgress;
  error?: string | null;
};

function OpportunityRow({ opportunity }: { opportunity: XpOpportunity }) {
  return (
    <p className="xp-progress-detail-value xp-progress-action-row">
      <span className="xp-progress-action-label">{opportunity.label}</span>
      <span className="xp-progress-award">+{numberFormatter.format(opportunity.xp)} XP</span>
    </p>
  );
}

export function XpProgressCardSkeleton() {
  return (
    <article className="status-card overview-command-card xp-progress-card xp-progress-card-skeleton" aria-busy="true">
      <div className="xp-progress-heading">
        <div className="xp-progress-skeleton-heading">
          <Skeleton variant="text" width={92} height={11} />
          <Skeleton variant="text" width={58} height={14} />
        </div>
        <Skeleton variant="block" width={74} height={20} style={{ borderRadius: 999 }} />
      </div>
      <div className="xp-progress-skeleton-total">
        <Skeleton variant="text" width="42%" height={44} />
      </div>
      <div className="xp-progress-skeleton-track">
        <Skeleton variant="block" width="100%" height={9} style={{ borderRadius: 999 }} />
      </div>
      <div className="xp-progress-skeleton-meta">
        <Skeleton variant="text" width={86} height={14} />
        <Skeleton variant="text" width={104} height={14} />
      </div>
      <div className="xp-progress-details">
        <section className="xp-progress-detail">
          <Skeleton variant="text" width={48} height={10} />
          <Skeleton variant="text" width="88%" height={14} />
        </section>
        <section className="xp-progress-detail">
          <Skeleton variant="text" width={74} height={10} />
          <Skeleton variant="text" width="82%" height={14} />
        </section>
      </div>
    </article>
  );
}

export function XpProgressCardView({ progress, error = null }: XpProgressCardViewProps) {
  const level = useMemo(() => resolveXpLevel(progress.state.totalXp), [progress.state.totalXp]);
  const ratio = level.nextLevel
    ? `${numberFormatter.format(progress.state.totalXp)} / ${numberFormatter.format(level.nextLevel.threshold)} XP`
    : null;
  const progressMaximum = level.nextLevel ? level.xpForNextLevel : 100;
  const progressNow = level.nextLevel ? level.xpWithinLevel : 100;
  const progressText = level.nextLevel
    ? `${numberFormatter.format(level.xpRemaining)} XP to Level ${level.nextLevel.level}`
    : "Maximum level reached";
  const progressRemaining = level.nextLevel
    ? `${numberFormatter.format(level.xpRemaining)} XP remaining`
    : "Max level reached";
  const [primaryOpportunity, ...remainingOpportunities] = progress.opportunities;

  return (
    <Link href="/progress" className="xp-progress-card-link" aria-label="Open XP progress">
      <article className="status-card overview-command-card xp-progress-card">
        <div className="xp-progress-heading">
          <div>
            <p className="status-label">XP PROGRESS</p>
            <p className="xp-progress-level">Level {level.currentLevel.level}</p>
          </div>
          <p className="xp-progress-rank">{level.currentLevel.title}</p>
        </div>

        <p
          className="xp-progress-total"
          aria-label={`${numberFormatter.format(progress.state.totalXp)} experience points`}
        >
          <span className="xp-progress-number">{numberFormatter.format(progress.state.totalXp)}</span>
          <span className="xp-progress-unit">XP</span>
        </p>

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

        <p className="xp-progress-meta">
          {ratio ? <span className="xp-progress-ratio">{ratio}</span> : null}
          <span>{progressRemaining}</span>
        </p>

        <div className="xp-progress-details">
          <section className="xp-progress-detail" aria-labelledby="xp-next-label">
            <p id="xp-next-label" className="xp-progress-section-label">NEXT</p>
            {primaryOpportunity ? (
              <OpportunityRow opportunity={primaryOpportunity} />
            ) : (
              <p className="xp-progress-detail-value xp-progress-empty">No XP action is due right now.</p>
            )}
          </section>

          <section className="xp-progress-detail" aria-labelledby="xp-more-label">
            <p id="xp-more-label" className="xp-progress-section-label">MORE XP</p>
            {remainingOpportunities.length > 0 ? (
              <div className="xp-progress-action-list">
                {remainingOpportunities.map((opportunity) => (
                  <OpportunityRow key={opportunity.code} opportunity={opportunity} />
                ))}
              </div>
            ) : (
              <p className="xp-progress-detail-value xp-progress-empty">No other action is due.</p>
            )}
          </section>
        </div>

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
