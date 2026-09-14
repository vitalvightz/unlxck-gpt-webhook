"use client";

import Link from "next/link";
import { useMemo } from "react";

import { useAppSession } from "@/components/auth-provider";
import { Skeleton } from "@/components/skeleton";
import { XpProgressCardSkeleton, XpProgressCardView } from "@/components/xp-progress-card";
import { useXp } from "@/components/xp-provider";
import { isSafeAvatarImageUrl } from "@/lib/avatar-image-url";
import {
  getOptionLabels,
  TACTICAL_STYLE_OPTIONS,
  TECHNICAL_STYLE_OPTIONS,
} from "@/lib/intake-options";
import { XP_ACTIONS } from "@/lib/xp";
import { useTranslations as useAppTranslations } from "next-intl";


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

function titleCase(value: string): string {
  return value
    .trim()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function getInitials(name: string): string {
  const initials = name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");

  return initials || "A";
}

function RefreshIcon() {
  return (
    <svg viewBox="0 0 20 20" width="18" height="18" fill="none" aria-hidden="true" focusable="false">
      <path
        d="M15.4 6.4A6.5 6.5 0 1 0 16.2 12M15.4 6.4V2.8M15.4 6.4h-3.6"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ProgressSkeleton() {
  return (
    <div className="xp-page xp-page--refined" aria-busy="true">
      <section className="xp-athlete-header">
        <Skeleton variant="block" width={52} height={52} style={{ borderRadius: 999 }} />
        <div className="xp-athlete-skeleton-copy">
          <Skeleton variant="text" width={72} height={10} />
          <Skeleton variant="text" width="46%" height={26} />
          <Skeleton variant="text" width="62%" height={13} />
        </div>
      </section>
      <XpProgressCardSkeleton mode="page" />
      <section className="xp-page-grid xp-page-summary-grid">
        {[0, 1].map((item) => (
          <article key={item} className="xp-page-panel">
            <Skeleton variant="text" width={100} height={11} />
            <Skeleton variant="text" width="72%" height={20} />
            <Skeleton variant="text" width="58%" height={14} />
          </article>
        ))}
      </section>
    </div>
  );
}

export default function ProgressPage() {
    const appText = useAppTranslations("AppText");
  const { session, isReady, isMeHydrated, me } = useAppSession();
  const xp = useXp();

  const fighterIdentity = useMemo(() => {
    if (!me) return [];

    const profile = me.profile;
    const labels = [
      ...getOptionLabels(TECHNICAL_STYLE_OPTIONS, profile.technical_style),
      ...getOptionLabels(TACTICAL_STYLE_OPTIONS, profile.tactical_style),
      profile.stance ? titleCase(profile.stance) : "",
    ].filter(Boolean);

    return [...new Set(labels)];
  }, [me]);

  if (!isReady || (session && !isMeHydrated) || !xp.isHydrated) {
    return <ProgressSkeleton />;
  }

  if (!session || !me || me.profile.role !== "athlete") {
    return (
      <section className="panel loading-card">
        <p className="kicker">{appText("text_4664827f8e89")}</p>
        <h1>{appText("text_676c825a0c1d")}</h1>
        <p className="muted">{appText("text_c299c4f53a14")}</p>
        <Link href="/login" className="cta">{appText("text_bfd402b2f6f3")}</Link>
      </section>
    );
  }

  const profile = me.profile;
  const athleteName = profile.full_name.trim() || appText("text_433a720b7e1d");
  const avatarUrl = isSafeAvatarImageUrl(profile.avatar_url) ? profile.avatar_url : null;
  const statusAndRecord = [
    profile.professional_status ? titleCase(profile.professional_status) : "",
    profile.record?.trim() || "",
  ].filter(Boolean);
  const visibleAwards = xp.progress.state.recentAwards.slice(0, 3);

  return (
    <div className="xp-page xp-page--refined">
      <header className="xp-athlete-header">
        <div className="xp-athlete-avatar" aria-hidden="true">
          {avatarUrl ? (
            <img src={avatarUrl} alt="" />
          ) : (
            <span>{getInitials(athleteName)}</span>
          )}
        </div>

        <div className="xp-athlete-identity">
          <p className="status-label">{appText("text_e0d0adc74c8b")}</p>
          <h1>{athleteName}</h1>
          {fighterIdentity.length > 0 ? (
            <p className="xp-athlete-style-line">{fighterIdentity.join(" · ")}</p>
          ) : (
            <p className="xp-athlete-style-line">{appText("text_3c1ece6cefbd")}</p>
          )}
          {statusAndRecord.length > 0 ? (
            <p className="xp-athlete-record-line">{statusAndRecord.join(" · ")}</p>
          ) : null}
        </div>

        <button
          type="button"
          className="xp-refresh-button"
          onClick={() => void xp.refresh()}
          disabled={xp.isRefreshing}
          aria-label={xp.isRefreshing ? appText("text_eb4a18a43b29") : appText("text_a8d1ab17b706")}
        >
          <RefreshIcon />
        </button>
      </header>

      {xp.error ? (
        <div className="xp-page-notice" role="status">
          {xp.error} {appText("text_4286c0790c74")}</div>
      ) : null}

      <XpProgressCardView progress={xp.progress} mode="page" />

      <section className="xp-page-grid xp-page-summary-grid">
        <article className="xp-page-panel xp-week-panel" aria-labelledby="xp-week-title">
          <div className="xp-page-section-heading">
            <div>
              <p className="status-label">{appText("text_7192a603df72")}</p>
              <h2 id="xp-week-title">
                {xp.progress.currentWeek
                  ? `Week ${
                      xp.progress.currentWeek.weekIndex === null
                        ? ""
                        : xp.progress.currentWeek.weekIndex + 1
                    }${xp.progress.currentWeek.phaseLabel ? ` — ${xp.progress.currentWeek.phaseLabel}` : ""}`
                  : appText("text_c0ea145314fc")}
              </h2>
            </div>
          </div>
          {xp.progress.currentWeek ? (
            <>
              <p className="xp-week-count">
                <strong>{xp.progress.currentWeek.completedSessions}</strong>
                <span>{appText("text_8a5edab28263")}{xp.progress.currentWeek.plannedSessions} {appText("text_1225ae6c1ae6")}</span>
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
                    ? appText("text_608f7de283ef")
                    : appText("text_d0b2f5857884")
                  : `${xp.progress.currentWeek.remainingSessions} session${
                      xp.progress.currentWeek.remainingSessions === 1 ? "" : "s"
                    } remaining. +100 XP when complete.`}
              </p>
            </>
          ) : (
            <p className="xp-page-empty">{appText("text_3167d590f40d")}</p>
          )}
        </article>

        <article className="xp-page-panel" aria-labelledby="xp-milestones-title">
          <div className="xp-page-section-heading">
            <div>
              <p className="status-label">{appText("text_2d973495c853")}</p>
              <h2 id="xp-milestones-title">{appText("text_92c27902b812")}</h2>
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
            <p className="xp-page-empty">{appText("text_6611c330ad76")}</p>
          )}
        </article>
      </section>

      <section className="xp-page-panel xp-awards-panel" aria-labelledby="xp-awards-title">
        <div className="xp-page-section-heading">
          <div>
            <p className="status-label">{appText("text_bf780a889b05")}</p>
            <h2 id="xp-awards-title">{appText("text_d14c0f9e186d")}</h2>
          </div>
          <span>{appText("text_6f87535d74dc")}</span>
        </div>
        {visibleAwards.length > 0 ? (
          <div className="xp-award-list">
            {visibleAwards.map((award) => (
              <div key={award.id} className="xp-award-row">
                <div>
                  <strong>{XP_ACTIONS[award.action].label}</strong>
                  <span>{dateTimeFormatter.format(new Date(award.awardedAt))}</span>
                </div>
                <span className="xp-award-amount">{appText("text_a318c24216de")}{numberFormatter.format(award.amount)} {appText("text_168aad3e9812")}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="xp-page-empty">{appText("text_f92104a23838")}</p>
        )}
      </section>

      <details className="xp-page-panel xp-explanation xp-explanation-disclosure">
        <summary>
          <span>
            <span className="status-label">{appText("text_2066aa9a84d1")}</span>
            <strong>{appText("text_28251bb05094")}</strong>
          </span>
          <span className="xp-details-chevron" aria-hidden="true">{appText("text_641b9bedb453")}</span>
        </summary>
        <div className="xp-explanation-content">
          <p>{appText("text_84e59f63361b")}</p>
          <p>{appText("text_01d3eda3c5ea")}</p>
          <p>{appText("text_6215eaca2236")}</p>
          <p>{appText("text_f1a2d1978fc8")}</p>
        </div>
      </details>
    </div>
  );
}
