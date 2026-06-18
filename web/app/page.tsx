"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAppSession } from "@/components/auth-provider";
import { PlansFeaturedSkeleton, Skeleton } from "@/components/skeleton";
import { getToday } from "@/lib/api";
import { formatPlanFightDate } from "@/lib/plan-format";
import {
  getActivePlanHref,
  getCompletionLabel,
  getRecommendationCopy,
  getSessionTitle,
  getVisibleRiskWatch,
  hasActivePlan,
} from "@/lib/today";
import type { TodayCommandView } from "@/lib/types";

const landingPreviewStages = [
  {
    label: "Advanced Intake",
    title: "Guided athlete intake",
    summary: "Capture profile, fight context, availability, and restrictions in one structured flow.",
    highlights: ["Profile + camp setup", "Training + restrictions"],
  },
  {
    label: "Nutrition",
    title: "Readiness stays connected",
    summary: "Weight setup, bodyweight logs, and nutrition readiness live beside the camp workflow.",
    highlights: ["Weight targets", "Daily readiness"],
  },
  {
    label: "Plans",
    title: "The latest camp reopens fast",
    summary: "Saved history and the latest plan stay attached to the athlete account.",
    highlights: ["Plan history", "In-app display"],
  },
] as const;

const landingProofPoints = [
  {
    label: "Saved history",
    title: "Every generated camp stays attached to the athlete account.",
    body: "Reopen the latest version fast without rebuilding context from scratch.",
  },
  {
    label: "Structured planning",
    title: "The intake is organized enough to catch gaps before generation.",
    body: "Fight context, training load, restrictions, and performance goals stay in one flow.",
  },
  {
    label: "Built for return visits",
    title: "The workspace makes it easy to resume, review, and export between sessions.",
    body: "Mobile-friendly access means the product still works when athletes are away from a desk.",
  },
] as const;

const landingWorkflowSteps = [
  {
    label: "Step 1",
    title: "Set up the athlete profile",
    body: "Create the account, capture the athlete profile, and save the draft as you go.",
  },
  {
    label: "Step 2",
    title: "Review readiness and restrictions",
    body: "Keep nutrition, fight context, and safety signals connected before generation.",
  },
  {
    label: "Step 3",
    title: "Generate and reopen camps",
    body: "Turn the intake into a saved camp plan, then return to the latest version any time.",
  },
] as const;

function formatTrainingDay(value: string | null | undefined): string {
  if (!value) {
    return "Today";
  }
  const date = new Date(`${value}T12:00:00`);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "short",
    day: "2-digit",
    month: "short",
  }).format(date);
}

function formatSessionDayLabel(session: TodayCommandView["today"]["next_session"]): string {
  const parts = [
    session.weekday_with_label || session.weekday,
    session.calendar_date ? formatTrainingDay(session.calendar_date) : null,
    typeof session.d_day === "number" ? `D-${Math.abs(session.d_day)}` : session.day_label,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "Scheduled session";
}

function hasNextSession(session: TodayCommandView["today"]["next_session"]): boolean {
  return Boolean(session.session_id || session.title || session.weekday || session.status);
}

// Overview command-centre risk watch: top 1-2 risks + "+N more". Read-only,
// mirrors Today; meaning never relies on colour alone (icon + label + text).
function OverviewRiskWatch({ risks }: { risks: TodayCommandView["risk_watch"] }) {
  if (!risks.length) {
    return null;
  }
  const { visible, overflow } = getVisibleRiskWatch(risks);
  return (
    <section className="overview-command-card overview-risk-watch" aria-label="Risk watch">
      <p className="kicker">Risk watch</p>
      <div className="today-risk-watch">
        {visible.map((risk) => (
          <article key={`${risk.category}-${risk.label}`} className="today-risk-item" data-tone={risk.tone}>
            <span className="today-risk-icon" aria-hidden="true">
              {risk.icon.replace(/-/g, " ").slice(0, 4).toUpperCase()}
            </span>
            <div>
              <p className="today-risk-label">{risk.label}</p>
              <p className="today-risk-text">{risk.text || "Monitor this before training."}</p>
            </div>
          </article>
        ))}
        {overflow > 0 ? <span className="today-risk-more">+{overflow} more</span> : null}
      </div>
    </section>
  );
}

function CommandCentreSkeleton() {
  return (
    <section className="hero-panel overview-command-shell athlete-motion-slot athlete-motion-header" aria-busy="true">
      <div className="overview-command-grid">
        <div className="hero-panel-copy overview-command-copy">
          <Skeleton variant="text" width={120} height={12} />
          <Skeleton variant="text" width="68%" height={42} />
          <Skeleton variant="text" width="82%" height={16} />
        </div>
        <PlansFeaturedSkeleton />
      </div>
    </section>
  );
}

// The Block 4 Overview command centre. Read-only: it mirrors the active-plan
// command view (no check-in form, no completion buttons, no raw structured_plan)
// and routes the athlete to Today / the active plan.
function CommandCentre({ state }: { state: TodayCommandView }) {
  const activePlan = state.active_plan;
  const planActive = hasActivePlan(activePlan);
  const recommendation = getRecommendationCopy(state.today.recommendation_state);
  const session = state.today.next_session;
  const notCheckedIn = state.today.recommendation_state === "not_checked_in";

  if (!planActive) {
    return (
      <section className="hero-panel overview-command-shell athlete-motion-slot athlete-motion-header">
        <div className="hero-panel-copy overview-command-copy">
          <p className="eyebrow">Camp command centre</p>
          <h1 className="hero-title">No active plan yet.</h1>
          <p className="overview-command-summary">
            Complete intake to generate the plan that drives Today and this command centre.
          </p>
          <div className="hero-actions">
            <Link href="/onboarding" className="cta">
              Complete Intake
            </Link>
            <Link href="/quick-build" className="ghost-button">
              Quick Build — 2 min
            </Link>
          </div>
        </div>
      </section>
    );
  }

  const headerItems = [
    { label: "Phase", value: activePlan.phase || "Current phase" },
    { label: "Training day", value: formatTrainingDay(state.today.training_day) },
    { label: "Fight date", value: formatPlanFightDate(activePlan.fight_date ?? null) },
  ];

  const primaryCtaLabel = notCheckedIn ? "Open Today / Check in" : "Open Today";

  return (
    <section className="overview-command-stack">
      <header className="hero-panel overview-command-shell athlete-motion-slot athlete-motion-header">
        <div className="hero-panel-copy overview-command-copy">
          <p className="eyebrow">Camp command centre</p>
          <h1 className="hero-title">{activePlan.name?.trim() || "Active fight camp"}</h1>
          <div className="overview-operational-strip" aria-label="Camp status">
            {headerItems.map((item) => (
              <div key={item.label} className="overview-operational-item">
                <span className="overview-operational-label">{item.label}</span>
                <span className="overview-operational-value">{item.value}</span>
              </div>
            ))}
          </div>
        </div>
      </header>

      <div className="overview-command-row">
        <section
          className="overview-command-card overview-today-state"
          data-tone={recommendation.tone}
          aria-labelledby="overview-today-state-heading"
        >
          <p className="kicker">Today&apos;s state</p>
          <h2 id="overview-today-state-heading" className="plan-summary-title">
            {recommendation.label}
          </h2>
          <p className="muted">{state.today.recommendation_reason || recommendation.actionText}</p>
          <div className="plan-summary-actions">
            <Link href="/dashboard" className="cta overview-primary-action">
              {primaryCtaLabel}
            </Link>
            <Link href={getActivePlanHref(activePlan)} className="secondary-button">
              View active plan
            </Link>
          </div>
        </section>

        <section className="overview-command-card overview-next-session" aria-labelledby="overview-next-session-heading">
          <p className="kicker">Next session</p>
          {hasNextSession(session) ? (
            <>
              <h2 id="overview-next-session-heading" className="plan-summary-title">
                {getSessionTitle(session)}
              </h2>
              <div className="overview-decision-strip" aria-label="Next session details">
                <div className="overview-decision-item">
                  <span className="overview-operational-label">When</span>
                  <span className="overview-operational-value">{formatSessionDayLabel(session)}</span>
                </div>
                {session.primary_focus || session.emphasis ? (
                  <div className="overview-decision-item">
                    <span className="overview-operational-label">Focus</span>
                    <span className="overview-operational-value">
                      {session.primary_focus || session.emphasis}
                    </span>
                  </div>
                ) : null}
                <div className="overview-decision-item">
                  <span className="overview-operational-label">Status</span>
                  <span className="overview-operational-value">
                    {getCompletionLabel(state.today.completion_status)}
                  </span>
                </div>
              </div>
              <div className="plan-summary-actions">
                <Link href="/dashboard" className="secondary-button">
                  Open Today
                </Link>
              </div>
            </>
          ) : (
            <>
              <h2 id="overview-next-session-heading" className="plan-summary-title">
                No session scheduled
              </h2>
              <p className="muted">Keep recovery work available and check Today for the next training target.</p>
              <div className="plan-summary-actions">
                <Link href="/dashboard" className="secondary-button">
                  Open Today
                </Link>
              </div>
            </>
          )}
        </section>
      </div>

      <OverviewRiskWatch risks={state.risk_watch} />
    </section>
  );
}

export default function HomePage() {
  const { isReady, isMeHydrated, hasTransientMeError, session, me, signOut } = useAppSession();
  const router = useRouter();
  const [activePreviewIndex, setActivePreviewIndex] = useState(0);
  const [previewPausedUntil, setPreviewPausedUntil] = useState(0);
  const [commandView, setCommandView] = useState<TodayCommandView | null>(null);
  const [commandStatus, setCommandStatus] = useState<"loading" | "ready" | "error">("loading");

  function setPreviewIndex(nextIndex: number) {
    const totalStages = landingPreviewStages.length;
    setActivePreviewIndex((nextIndex + totalStages) % totalStages);
    setPreviewPausedUntil(Date.now() + 9000);
  }

  function showPreviousPreview() {
    setPreviewIndex(activePreviewIndex - 1);
  }

  function showNextPreview() {
    setPreviewIndex(activePreviewIndex + 1);
  }

  useEffect(() => {
    if (session) {
      return;
    }

    const intervalId = window.setInterval(() => {
      if (document.hidden || Date.now() < previewPausedUntil) {
        return;
      }
      setActivePreviewIndex((currentIndex) => (currentIndex + 1) % landingPreviewStages.length);
    }, 4500);

    return () => window.clearInterval(intervalId);
  }, [previewPausedUntil, session]);

  useEffect(() => {
    if (isReady && session && isMeHydrated && !me) {
      router.replace("/login");
    }
  }, [isReady, isMeHydrated, me, router, session]);

  // Overview is a read-only mirror of the active-plan command view. It never
  // parses structured_plan, never computes readiness, and never mutates state.
  useEffect(() => {
    const token = session?.access_token;
    if (!token || !me) {
      return;
    }
    let active = true;
    setCommandStatus("loading");
    void getToday(token)
      .then((view) => {
        if (!active) {
          return;
        }
        setCommandView(view);
        setCommandStatus("ready");
      })
      .catch(() => {
        if (!active) {
          return;
        }
        setCommandStatus("error");
      });
    return () => {
      active = false;
    };
  }, [me, session?.access_token]);

  if (session && hasTransientMeError) {
    return (
      <section className="panel loading-card">
        <p className="kicker">Overview</p>
        <h1>Workspace temporarily unavailable</h1>
        <p className="muted">Your session exists, but the app could not load your athlete profile.</p>
        <div className="hero-actions">
          <button type="button" className="cta" onClick={() => window.location.reload()}>
            Retry
          </button>
          <button type="button" className="secondary-button" onClick={() => void signOut()}>
            Sign out
          </button>
        </div>
      </section>
    );
  }

  if (!isReady) {
    return (
      <section className="panel loading-card">
        <p className="kicker">Overview</p>
        <h1>Loading your camp command centre</h1>
        <p className="muted">Checking your active plan and today&apos;s state.</p>
      </section>
    );
  }

  if (session && !isMeHydrated) {
    return <CommandCentreSkeleton />;
  }

  if (session && isMeHydrated && !me) {
    return (
      <section className="panel loading-card">
        <p className="kicker">Overview</p>
        <h1>Redirecting to login</h1>
        <p className="muted">Session expired. Sign in again.</p>
      </section>
    );
  }

  if (session && me) {
    const latestPlan = me.latest_plan ?? null;
    const draft = (me.profile.onboarding_draft as { current_step?: number } | null) ?? null;
    const latestIntake = me.latest_intake;
    const hasMeaningfulDraft = Boolean(
      draft && typeof draft === "object" && Object.keys(draft as Record<string, unknown>).length > 0,
    );
    const isFirstTimeUser =
      me.plan_count === 0 && !latestPlan && !latestIntake && !hasMeaningfulDraft;

    if (isFirstTimeUser) {
      return (
        <section className="hero-panel welcome-panel athlete-motion-slot athlete-motion-header">
          <div className="hero-panel-copy welcome-copy">
            <p className="eyebrow">Welcome to UNLXCK</p>
            <h1 className="hero-title">Build your fight camp in minutes.</h1>
            <p className="overview-command-summary">
              Create your athlete profile, generate a structured camp plan, and manage your setup from one dashboard.
            </p>
            <p className="muted welcome-context">
              Designed for fighters and combat athletes. Quick Build takes about 2 minutes. Advanced Intake gives more control.
            </p>
            <div className="hero-actions welcome-actions">
              <Link href="/onboarding" className="cta">
                Start Advanced Intake
              </Link>
              <Link href="/quick-build" className="secondary-button">
                Use Quick Build
              </Link>
              <Link href="/demo-plan" className="ghost-button">
                View Demo Plan
              </Link>
            </div>
          </div>
        </section>
      );
    }

    if (commandStatus === "loading" && !commandView) {
      return <CommandCentreSkeleton />;
    }

    if (commandStatus === "error" && !commandView) {
      return (
        <section className="panel loading-card">
          <p className="kicker">Camp command centre</p>
          <h1>Overview did not load</h1>
          <p className="muted" role="alert">Could not load your camp status. Try again in a moment.</p>
          <div className="hero-actions">
            <Link href="/dashboard" className="cta">
              Open Today
            </Link>
            <Link href="/plans" className="secondary-button">
              Plan workspace
            </Link>
          </div>
        </section>
      );
    }

    if (commandView) {
      return <CommandCentre state={commandView} />;
    }

    return <CommandCentreSkeleton />;
  }

  const activePreviewStage = landingPreviewStages[activePreviewIndex];

  return (
    <>
      <section className="hero-panel public-hero-panel">
        <div className="public-hero-grid">
          <div className="hero-panel-copy public-hero-copy">
            <p className="eyebrow">Athlete-first beta</p>
            <h1 className="hero-title">See the camp workflow before you sign up.</h1>
            <p className="public-hero-summary">UNLXCK brings intake, readiness, generation, and saved history into one athlete workspace instead of scattering them across notes and forms.</p>
            <div className="hero-actions">
              <Link href="/signup" className="cta">
                Start free beta
              </Link>
              <Link href="/login" className="ghost-button">
                Log in
              </Link>
            </div>
            <div className="public-proof-strip" aria-label="Product highlights">
              <div className="public-proof-pill">
                <span className="label">Structured intake</span>
                <span className="public-proof-value">Profile, camp context, and restrictions in one flow</span>
              </div>
              <div className="public-proof-pill">
                <span className="label">Saved plans</span>
                <span className="public-proof-value">Latest camp and history stay attached</span>
              </div>
              <div className="public-proof-pill">
                <span className="label">Built to return to</span>
                <span className="public-proof-value">Resume the next task fast on desktop or mobile</span>
              </div>
            </div>
          </div>

          <article className="support-panel public-preview-panel">
            <div className="public-preview-header">
              <div>
                <p className="kicker">Product preview</p>
                <h2 className="form-section-title">What the workspace actually looks like</h2>
              </div>
              <span className="badge status-badge-neutral">Live flow</span>
            </div>
            <div className="public-preview-window">
              <div className="public-preview-toolbar">
                {landingPreviewStages.map((stage, index) => (
                  <button
                    key={stage.label}
                    type="button"
                    className={index === activePreviewIndex ? "public-preview-dot public-preview-dot-active" : "public-preview-dot"}
                    aria-label={`Show ${stage.label}`}
                    aria-pressed={index === activePreviewIndex}
                    onClick={() => setPreviewIndex(index)}
                  />
                ))}
                <span className="public-preview-toolbar-label">Athlete workspace</span>
              </div>
              <div className="public-preview-carousel" aria-live="polite">
                <article key={activePreviewStage.label} className="public-preview-card">
                  <div className="public-preview-card-header">
                    <div>
                      <p className="label">{activePreviewStage.label}</p>
                      <h3 className="public-preview-card-title">{activePreviewStage.title}</h3>
                    </div>
                  </div>
                  <p className="muted">{activePreviewStage.summary}</p>
                  <div className="public-preview-chip-row">
                    {activePreviewStage.highlights.map((highlight) => (
                      <span key={highlight} className="public-preview-chip">
                        {highlight}
                      </span>
                    ))}
                  </div>
                </article>
              </div>
              <div className="public-preview-controls" aria-label="Product preview controls">
                <button type="button" className="public-preview-control" aria-label="Previous preview" onClick={showPreviousPreview}>
                  <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">
                    <path d="M12.5 4.5 7 10l5.5 5.5" />
                  </svg>
                </button>
                <div className="public-preview-progress" aria-hidden="true">
                  {landingPreviewStages.map((stage, index) => (
                    <span
                      key={`${stage.label}-progress`}
                      className={
                        index === activePreviewIndex
                          ? "public-preview-progress-segment public-preview-progress-segment-active"
                          : "public-preview-progress-segment"
                      }
                    />
                  ))}
                </div>
                <button type="button" className="public-preview-control" aria-label="Next preview" onClick={showNextPreview}>
                  <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">
                    <path d="m7.5 4.5 5.5 5.5-5.5 5.5" />
                  </svg>
                </button>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section className="public-proof-grid" aria-label="Trust and proof points">
        {landingProofPoints.map((point) => (
          <article key={point.title} className="support-panel public-proof-card">
            <p className="kicker">{point.label}</p>
            <h2 className="form-section-title">{point.title}</h2>
            <p className="muted">{point.body}</p>
          </article>
        ))}
      </section>

      <section className="public-section-break" aria-labelledby="public-journey-heading">
        <div className="public-section-break-line" aria-hidden="true" />
        <div className="public-section-break-copy">
          <p className="kicker">How it starts</p>
          <h2 id="public-journey-heading">From setup to saved camp.</h2>
        </div>
        <div className="public-section-break-count" aria-hidden="true">03</div>
      </section>

      <section className="metric-grid public-journey-grid">
        {landingWorkflowSteps.map((step) => (
          <article key={step.title} className="support-panel">
            <div className="form-section-header">
              <p className="kicker">{step.label}</p>
              <h2 className="form-section-title">{step.title}</h2>
            </div>
            <p className="muted">{step.body}</p>
          </article>
        ))}
      </section>
    </>
  );
}
