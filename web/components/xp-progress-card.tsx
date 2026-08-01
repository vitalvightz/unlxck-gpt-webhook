"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";

import { Skeleton } from "@/components/skeleton";
import { useXp, type XpDailyRewardStatus } from "@/components/xp-provider";
import { XP_ACTIONS, resolveXpLevel, type XpState } from "@/lib/xp";

const XP_TOTAL_ANIMATION_MS = 640;
const numberFormatter = new Intl.NumberFormat("en-GB");

export type XpProgressCardViewProps = {
  state: XpState;
  dailyRewardStatus: XpDailyRewardStatus;
  isNewAward?: boolean;
  isNewDailyAward?: boolean;
  previousTotalXp?: number;
};

export function prefersReducedXpMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/* Mirrors the card's structure exactly so hydration swaps content into a row
   that is already the right height. */
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
          <Skeleton variant="text" width={92} height={10} />
          <Skeleton variant="text" width="80%" height={14} />
        </section>
        <section className="xp-progress-detail">
          <Skeleton variant="text" width={56} height={10} />
          <Skeleton variant="text" width="88%" height={14} />
        </section>
      </div>
    </article>
  );
}

export function XpProgressCardView({
  state,
  dailyRewardStatus,
  isNewAward = false,
  isNewDailyAward = false,
  previousTotalXp = state.totalXp,
}: XpProgressCardViewProps) {
  const progress = useMemo(() => resolveXpLevel(state.totalXp), [state.totalXp]);
  const previousProgress = useMemo(
    () => resolveXpLevel(isNewAward ? previousTotalXp : 0),
    [isNewAward, previousTotalXp],
  );
  const startPercentage = isNewAward ? previousProgress.percentage : 0;
  const [displayPercentage, setDisplayPercentage] = useState(startPercentage);
  const [displayTotal, setDisplayTotal] = useState(isNewAward ? previousTotalXp : state.totalXp);

  useEffect(() => {
    const reduceMotion = prefersReducedXpMotion();
    let cancelled = false;
    let progressFrame = 0;
    let countFrame = 0;

    queueMicrotask(() => {
      if (cancelled) return;
      if (reduceMotion) {
        setDisplayPercentage(progress.percentage);
        setDisplayTotal(state.totalXp);
        return;
      }

      setDisplayPercentage(startPercentage);
      setDisplayTotal(isNewAward ? previousTotalXp : state.totalXp);
      progressFrame = window.requestAnimationFrame(() => setDisplayPercentage(progress.percentage));
      if (!isNewAward || previousTotalXp === state.totalXp) {
        setDisplayTotal(state.totalXp);
        return;
      }

      const animationStart = performance.now();
      const count = (timestamp: number) => {
        const elapsed = Math.min(1, (timestamp - animationStart) / XP_TOTAL_ANIMATION_MS);
        const eased = 1 - Math.pow(1 - elapsed, 3);
        setDisplayTotal(Math.round(previousTotalXp + (state.totalXp - previousTotalXp) * eased));
        if (elapsed < 1) {
          countFrame = window.requestAnimationFrame(count);
        }
      };
      countFrame = window.requestAnimationFrame(count);
    });

    return () => {
      cancelled = true;
      window.cancelAnimationFrame(progressFrame);
      window.cancelAnimationFrame(countFrame);
    };
  }, [isNewAward, previousTotalXp, progress.percentage, startPercentage, state.totalXp]);

  const progressMaximum = progress.nextLevel ? progress.xpForNextLevel : 100;
  const progressNow = progress.nextLevel ? progress.xpWithinLevel : 100;
  const progressLabel = progress.nextLevel
    ? `${progress.xpRemaining} XP to Level ${progress.nextLevel.level}`
    : "Max level reached";
  const dailyRewardAmount = XP_ACTIONS.daily_login.xp;

  /* At max level the ratio would just restate the total sitting directly above
     it, so the row carries the status alone. */
  const progressRatio = progress.nextLevel
    ? `${numberFormatter.format(progress.xpWithinLevel)} / ${numberFormatter.format(progress.xpForNextLevel)} XP`
    : null;
  const progressRemaining = progress.nextLevel
    ? `${numberFormatter.format(progress.xpRemaining)} XP remaining`
    : "Max level reached";

  /* The recent slot shows the latest award that is not the daily login already
     reported beside it, so the same +10 is never printed twice on a day when
     the login is the only thing earned. */
  const recentAward = useMemo(() => {
    const awards = [...state.recentAwards];
    if (dailyRewardStatus === "earned") {
      const claimedToday = awards.findIndex((award) => award.action === "daily_login");
      if (claimedToday !== -1) {
        awards.splice(claimedToday, 1);
      }
    }
    return awards[0] ?? null;
  }, [dailyRewardStatus, state.recentAwards]);

  return (
    <article
      className="status-card overview-command-card xp-progress-card"
      data-new-award={isNewAward ? "true" : undefined}
    >
      <div className="xp-progress-heading">
        <div>
          <p className="status-label">XP PROGRESS</p>
          <p className="xp-progress-level">Level {progress.currentLevel.level}</p>
        </div>
        <p className="xp-progress-rank">{progress.currentLevel.title}</p>
      </div>

      <p className="xp-progress-total" aria-label={`${numberFormatter.format(state.totalXp)} experience points`}>
        <span className="xp-progress-number">{numberFormatter.format(displayTotal)}</span>
        <span className="xp-progress-unit">XP</span>
      </p>

      <div
        className="xp-progress-track"
        role="progressbar"
        aria-label={progress.nextLevel ? `XP progress to Level ${progress.nextLevel.level}` : "Maximum XP level reached"}
        aria-valuemin={0}
        aria-valuemax={progressMaximum}
        aria-valuenow={progressNow}
        aria-valuetext={progressLabel}
      >
        <span
          className="xp-progress-fill"
          style={{ "--xp-progress-width": `${displayPercentage}%` } as CSSProperties}
        >
          <span className="xp-progress-shimmer" aria-hidden="true" />
        </span>
      </div>
      <p className="xp-progress-meta">
        {progressRatio ? <span className="xp-progress-ratio">{progressRatio}</span> : null}
        <span>{progressRemaining}</span>
      </p>

      <div className="xp-progress-details">
        <section className="xp-progress-detail" aria-labelledby="xp-daily-label">
          <p id="xp-daily-label" className="xp-progress-section-label">TODAY&apos;S REWARD</p>
          <p
            className="xp-progress-detail-value xp-progress-daily-value"
            data-new-reward={isNewDailyAward ? "true" : undefined}
          >
            {dailyRewardStatus === "earned" ? (
              <><span className="xp-progress-award">+{dailyRewardAmount} XP</span> claimed</>
            ) : dailyRewardStatus === "unavailable" ? (
              "Daily reward could not be saved"
            ) : (
              "Checking today's reward"
            )}
          </p>
        </section>

        <section className="xp-progress-detail" aria-labelledby="xp-recent-label">
          <p id="xp-recent-label" className="xp-progress-section-label">RECENT</p>
          {recentAward ? (
            <p className="xp-progress-detail-value xp-progress-recent">
              <span>{XP_ACTIONS[recentAward.action].label}</span>
              <span className="xp-progress-award">+{numberFormatter.format(recentAward.amount)} XP</span>
            </p>
          ) : (
            <p className="xp-progress-detail-value xp-progress-empty">No other XP yet</p>
          )}
        </section>
      </div>
    </article>
  );
}

export function XpProgressCard() {
  const xp = useXp();
  if (!xp.isHydrated) {
    return <XpProgressCardSkeleton />;
  }
  return (
    <XpProgressCardView
      state={xp.state}
      dailyRewardStatus={xp.dailyRewardStatus}
      isNewAward={xp.isNewAward}
      isNewDailyAward={xp.isNewDailyAward}
      previousTotalXp={xp.previousTotalXp}
    />
  );
}
