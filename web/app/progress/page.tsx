"use client";

import Link from "next/link";
import { useMemo } from "react";

import { useAppSession } from "@/components/auth-provider";
import { Skeleton } from "@/components/skeleton";
import { useXp } from "@/components/xp-provider";
import { XP_ACTIONS, resolveXpLevel } from "@/lib/xp";

const numberFormatter = new Intl.NumberFormat("en-GB");
const dateFormatter = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
});
const dateTimeFormatter = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

function ProgressSkeleton() {
  return (
    <div className="xp-page" aria-busy="true">
      <section className="xp-page-hero">
        <Skeleton variant="text" width={120} height={12} />
        <Skeleton variant="text" width="52%" height={54} />
        <Skeleton variant="block" width="100%" height={10} style={{ borderRadius: 999 }} />
      </section>
      <section className="xp-page-grid">
        {[0, 1, 2, 3].map((item) => (
          <article key={item} className="xp-page-panel">
            <Skeleton variant="text" width={100} height={14} />
            <Skeleton variant="text" width="80%" height={18} />
            <Skeleton variant="text" width="64%" height={18} />
          </article>
        ))}
      </section>
    </div>
  );
}

export default function ProgressPage() {
  const { session, isReady, isMeHydrated, me } = useAppSession();
  const xp = useXp();
  const level = useMemo(
    () => resolveXpLevel(xp.progress.state.totalXp),
    [xp.progress.state.totalXp],
  );

  if (!isReady || (session && !isMeHydrated) || !xp.isHydrated) {
    return <ProgressSkeleton />;
  }

  if (!session || !me || me.profile.role !== "athlete") {
    return (
      <section className="panel loading-card">
        <p className="kicker">Progress</p>
        <h1>Athlete account required</h1>
        <p className="muted">Sign in with an athlete account to view XP progress.</p>
        <Link href="/login" className="cta">Sign in</Link>
      </section>
    );
  }

  const total = xp.progress.state.totalXp;
  const nextThreshold = level.nextLevel?.threshold ?? level.currentLevel.threshold;
  const headlineRatio = level.nextLevel
    ? `${numberFormatter.format(total)} / ${numberFormatter.format(nextThreshold)} XP`
    : `${numberFormatter.format(total)} XP`;

  return (
    <div className="xp-page">
      <header className="xp-page-header">
        <div>
          <p className="kicker">Progress</p>
          <h1>Work banked. Level earned.</h1>
          <p className="muted">
            Your UNLXCK rank grows through completed training, useful check-ins and major plan milestones.
          </p>
        </div>
        <button
          type="button"
          className="secondary-button"
          onClick={() => void xp.refresh()}
          disabled={xp.isRefreshing}
        >
          {xp.isRefreshing ? "Refreshing…" : "Refresh"}
        </button>
      </header>

      {xp.error ? (
        <div className="xp-page-notice" role="status">
          {xp.error} The last valid progress view is still shown.
        </div>
      ) : null}

      <section className="xp-page-hero" aria-labelledby="xp-rank-heading">
        <div className="xp-page-rank-heading">
          <div>
            <p className="status-label">CURRENT UNLXCK RANK</p>
            <h2 id="xp-rank-heading">
              LEVEL {level.currentLevel.level} — {level.currentLevel.title.toUpperCase()}
            </h2>
          </div>
          <span className="xp-page-total">{numberFormatter.format(total)} XP</span>
        </div>
        <p className="xp-page-ratio">{headlineRatio}</p>
        <div
          className="xp-page-progress-track"
          role="progressbar"
          aria-label={level.nextLevel ? `Progress to ${level.nextLevel.title}` : "Maximum level reached"}
          aria-valuemin={0}
          aria-valuemax={level.nextLevel ? level.xpForNextLevel : 100}
          aria-valuenow={level.nextLevel ? level.xpWithinLevel : 100}
          aria-valuetext={
            level.nextLevel
              ? `${level.xpRemaining} XP to Level ${level.nextLevel.level}`
              : "Maximum level reached"
          }
        >
          <span style={{ width: `${level.percentage}%` }} />
        </div>
        <div className="xp-page-rank-meta">
          <span>
            {level.nextLevel
              ? `${numberFormatter.format(level.xpRemaining)} XP to ${level.nextLevel.title}`
              : "Maximum level reached"}
          </span>
          <span>{level.nextLevel ? `Next: Level ${level.nextLevel.level}` : "Champion"}</span>
        </div>
      </section>

      <section className="xp-page-panel xp-page-next" aria-labelledby="xp-next-title">
        <div className="xp-page-section-heading">
          <div>
            <p className="status-label">NEXT</p>
            <h2 id="xp-next-title">Available XP actions</h2>
          </div>
          <span>Only actions possible now</span>
        </div>
        {xp.progress.opportunities.length > 0 ? (
          <div className="xp-opportunity-list">
            {xp.progress.opportunities.map((opportunity) => (
              <Link key={opportunity.code} href={opportunity.href} className="xp-opportunity-row">
                <span className="xp-opportunity-amount">+{numberFormatter.format(opportunity.xp)} XP</span>
                <span>{opportunity.label}</span>
                <span aria-hidden="true">→</span>
              </Link>
            ))}
          </div>
        ) : (
          <p className="xp-page-empty">No XP action is due right now.</p>
        )}
      </section>

      <section className="xp-page-grid">
        <article className="xp-page-panel xp-week-panel" aria-labelledby="xp-week-title">
          <div className="xp-page-section-heading">
            <div>
              <p className="status-label">WEEKLY PROGRESS</p>
              <h2 id="xp-week-title">
                {xp.progress.currentWeek
                  ? `Week ${
                      xp.progress.currentWeek.weekIndex === null
                        ? ""
                        : xp.progress.currentWeek.weekIndex + 1
                    } ${xp.progress.currentWeek.phaseLabel ? `— ${xp.progress.currentWeek.phaseLabel}` : ""}`
                  : "No active training week"}
              </h2>
            </div>
          </div>
          {xp.progress.currentWeek ? (
            <>
              <p className="xp-week-count">
                <strong>{xp.progress.currentWeek.completedSessions}</strong>
                <span>/ {xp.progress.currentWeek.plannedSessions} planned sessions complete</span>
              </p>
              <div className="xp-week-track" aria-hidden="true">
                <span
                  style={{
                    width: `${
                      xp.progress.currentWeek.plannedSessions > 0
                        ? (xp.progress.currentWeek.completedSessions /
                            xp.progress.currentWeek.plannedSessions) *
                          100
                        : 0
                    }%`,
                  }}
                />
              </div>
              <p className="muted">
                {xp.progress.currentWeek.complete
                  ? xp.progress.currentWeek.weekXpEarned
                    ? "+100 XP earned for the completed week."
                    : "Week complete. XP reconciliation is pending."
                  : `${xp.progress.currentWeek.remainingSessions} session${
                      xp.progress.currentWeek.remainingSessions === 1 ? "" : "s"
                    } remaining. +100 XP when the week is complete.`}
              </p>
            </>
          ) : (
            <p className="xp-page-empty">Activate a structured plan to track weekly progress.</p>
          )}
        </article>

        <article className="xp-page-panel" aria-labelledby="xp-milestones-title">
          <div className="xp-page-section-heading">
            <div>
              <p className="status-label">MAJOR MILESTONES</p>
              <h2 id="xp-milestones-title">Plan journey</h2>
            </div>
          </div>
          {xp.progress.majorMilestones.length > 0 ? (
            <ol className="xp-milestone-list">
              {xp.progress.majorMilestones.map((milestone) => (
                <li key={`${milestone.milestoneType}:${milestone.planId}:${milestone.id}`}>
                  <span className="xp-milestone-dot" aria-hidden="true" />
                  <div>
                    <strong>{milestone.displayLabel}</strong>
                    <span>{dateFormatter.format(new Date(milestone.completedAt))}</span>
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <p className="xp-page-empty">Completed phases, plans and fight camps will appear here.</p>
          )}
        </article>
      </section>

      <section className="xp-page-panel" aria-labelledby="xp-awards-title">
        <div className="xp-page-section-heading">
          <div>
            <p className="status-label">RECENT AWARDS</p>
            <h2 id="xp-awards-title">Latest XP earned</h2>
          </div>
          <span>Latest 20</span>
        </div>
        {xp.progress.state.recentAwards.length > 0 ? (
          <div className="xp-award-list">
            {xp.progress.state.recentAwards.map((award) => (
              <div key={award.id} className="xp-award-row">
                <div>
                  <strong>{XP_ACTIONS[award.action].label}</strong>
                  <span>{dateTimeFormatter.format(new Date(award.awardedAt))}</span>
                </div>
                <span className="xp-award-amount">+{numberFormatter.format(award.amount)} XP</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="xp-page-empty">Complete your first real action to begin the ledger.</p>
        )}
      </section>

      <section className="xp-page-panel xp-explanation" aria-labelledby="xp-explanation-title">
        <p className="status-label">HOW XP WORKS</p>
        <h2 id="xp-explanation-title">Progress, not competitive status</h2>
        <p>
          UNLXCK rank reflects your progress and completed work inside UNLXCK. It is not an official amateur,
          professional or competitive ranking.
        </p>
        <ul>
          <li>XP is earned through real actions such as training, check-ins and completed plan milestones.</li>
          <li>Reopening the app does not generate XP.</li>
          <li>Repeating an already-recorded action does not duplicate XP.</li>
          <li>There is no public leaderboard during private beta.</li>
        </ul>
      </section>
    </div>
  );
}
