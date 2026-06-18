"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

import {
  BlockCard,
  NutritionCard,
  RecoveryCard,
} from "@/components/structured-plan-renderer";
import { formatPlanLabel } from "@/lib/plan-labels";
import { getPlanDisplayName } from "@/lib/plan-format";
import {
  cleanText,
  classifySessionlessDay,
  formatMeasured,
  getBlocks,
  getDays,
  getDeterministicNutritionPhases,
  getDeterministicRecoveryPhases,
  getDisplayableRedFlags,
  getFallbackSafetyNotes,
  getPlanNotes,
  getSessions,
  getWeeks,
  redFlagView,
  weekLabel,
} from "@/lib/structured-plan";
import type {
  PlanAdvisory,
  PlanDetail,
  StructuredDay,
  StructuredPlan,
  StructuredSession,
  StructuredWeek,
} from "@/lib/types";

const titleize = formatPlanLabel;
const COMPLETE_STATUS_RE = /\b(done|complete|completed)\b/i;
const HIGH_LOAD_RE = /\b(high|max|intense|neural|power|speed|sparring)\b/i;
const MODERATE_LOAD_RE = /\b(moderate|medium|tempo|technical)\b/i;
const LOW_LOAD_RE = /\b(low|easy|recovery|rest|off|mobility)\b/i;

type PlanCampMapProps = {
  plan: PlanDetail;
  structuredPlan: StructuredPlan | null;
  rawText: string;
  isActive: boolean;
  isArchived: boolean;
  canSetActive: boolean;
  setActivePending: boolean;
  activePlanError?: string | null;
  planActionPending?: "rename" | "archive" | "permanent-delete" | null;
  canManagePlan: boolean;
  canPermanentlyDelete: boolean;
  primaryAdvisory?: PlanAdvisory | null;
  onSetActive: () => void;
  onRename: () => void;
  onArchive: () => void;
  onPermanentDelete: () => void;
};

type WeekLoad = "High" | "Moderate" | "Low" | "Mixed";

function parseDate(value: string | null | undefined): Date | null {
  const text = cleanText(value);
  if (!text) {
    return null;
  }
  const timestamp = Date.parse(text);
  if (Number.isNaN(timestamp)) {
    return null;
  }
  const date = new Date(timestamp);
  date.setHours(0, 0, 0, 0);
  return date;
}

function todayDate(): Date {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return today;
}

function sameDay(left: Date | null, right: Date | null): boolean {
  return Boolean(left && right && left.getTime() === right.getTime());
}

function dayKey(day: StructuredDay, index: number): string {
  return cleanText(day.date) || cleanText(day.countdown_label) || `day-${index}`;
}

function sessionKey(session: StructuredSession, index: number): string {
  return cleanText(session.session_id) || cleanText(session.title) || `session-${index}`;
}

function formatDateLabel(value: string | null | undefined): string | null {
  const parsed = parseDate(value);
  if (!parsed) {
    return cleanText(value);
  }
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "short",
    day: "2-digit",
    month: "short",
  }).format(parsed);
}

function formatEventDate(value: string | null | undefined): string | null {
  const parsed = parseDate(value);
  if (!parsed) {
    return cleanText(value);
  }
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(parsed);
}

function weekNumber(week: StructuredWeek, index: number): number {
  return typeof week.week_index === "number" && week.week_index > 0 ? week.week_index : index + 1;
}

function isTodayInWeek(week: StructuredWeek, today: Date): boolean {
  const start = parseDate(week.start_date);
  const end = parseDate(week.end_date);
  if (start && end && today >= start && today <= end) {
    return true;
  }
  return getDays(week).some((day) => sameDay(parseDate(day.date), today));
}

function findInitialWeekIndex(weeks: StructuredWeek[], today: Date): number {
  const currentIndex = weeks.findIndex((week) => isTodayInWeek(week, today));
  if (currentIndex >= 0) {
    return currentIndex;
  }
  const upcomingIndex = weeks.findIndex((week) => {
    const end = parseDate(week.end_date);
    return Boolean(end && end >= today);
  });
  return upcomingIndex >= 0 ? upcomingIndex : 0;
}

function findDefaultDayKey(week: StructuredWeek | null | undefined, today: Date): string | null {
  const days = getDays(week);
  if (!days.length) {
    return null;
  }
  const currentIndex = days.findIndex((day) => sameDay(parseDate(day.date), today));
  if (currentIndex >= 0) {
    return dayKey(days[currentIndex], currentIndex);
  }
  const firstSessionIndex = days.findIndex((day) => getSessions(day).length > 0);
  const selectedIndex = firstSessionIndex >= 0 ? firstSessionIndex : 0;
  return dayKey(days[selectedIndex], selectedIndex);
}

function flattenDays(weeks: StructuredWeek[]): StructuredDay[] {
  return weeks.flatMap((week) => getDays(week));
}

function getCurrentDay(weeks: StructuredWeek[], selectedWeek: StructuredWeek | null): StructuredDay | null {
  const today = todayDate();
  return (
    flattenDays(weeks).find((day) => sameDay(parseDate(day.date), today)) ||
    getDays(selectedWeek).find((day) => getSessions(day).length > 0) ||
    getDays(selectedWeek)[0] ||
    null
  );
}

function firstSession(day: StructuredDay | null): StructuredSession | null {
  return getSessions(day)[0] || null;
}

function sessionTitle(session: StructuredSession | null, day?: StructuredDay | null): string {
  return (
    cleanText(session?.title) ||
    cleanText(day?.today_card?.headline) ||
    titleize(cleanText(session?.session_type) || "Session")
  );
}

function dayHeadline(day: StructuredDay): string {
  const session = firstSession(day);
  if (session) {
    return sessionTitle(session, day);
  }
  return classifySessionlessDay(day).title;
}

function completionLabel(sessions: StructuredSession[]): string {
  if (!sessions.length) {
    return "No app blocks";
  }
  const completed = sessions.filter((session) =>
    COMPLETE_STATUS_RE.test(cleanText(session.completion_status) || ""),
  ).length;
  return completed > 0 ? `${completed}/${sessions.length} done` : "Not started";
}

function weekCompletionLabel(week: StructuredWeek): string {
  const sessions = getDays(week).flatMap((day) => getSessions(day));
  if (!sessions.length) {
    return "No app blocks";
  }
  const completed = sessions.filter((session) =>
    COMPLETE_STATUS_RE.test(cleanText(session.completion_status) || ""),
  ).length;
  return completed > 0 ? `${completed}/${sessions.length} done` : `${sessions.length} sessions`;
}

function summarizeWeekLoad(week: StructuredWeek | null): WeekLoad {
  const source = getDays(week)
    .flatMap((day) => [
      day.day_type,
      day.today_card?.headline,
      ...getSessions(day).flatMap((session) => [
        session.primary_stressor,
        session.cns_demand,
        session.impact_level,
        session.objective,
        session.title,
      ]),
    ])
    .map((value) => cleanText(value))
    .filter((value): value is string => Boolean(value))
    .join(" ");

  if (HIGH_LOAD_RE.test(source)) {
    return "High";
  }
  if (MODERATE_LOAD_RE.test(source)) {
    return "Moderate";
  }
  if (LOW_LOAD_RE.test(source)) {
    return "Low";
  }
  return "Mixed";
}

function getPrimaryWarning(plan: StructuredPlan | null, day: StructuredDay | null): string | null {
  const dayWarning = cleanText(day?.today_card?.primary_warning) || cleanText(day?.today_card?.weight_cut_warning);
  if (dayWarning) {
    return dayWarning;
  }
  const redFlag = getDisplayableRedFlags(plan)[0];
  if (redFlag) {
    const view = redFlagView(redFlag);
    return view.text || view.action;
  }
  return getFallbackSafetyNotes(plan)[0]?.text || getPlanNotes(plan).find((note) => note.category === "injury")?.text || null;
}

function getCountdown(plan: StructuredPlan | null, selectedWeek: StructuredWeek | null): string | null {
  const currentDay = getCurrentDay(getWeeks(plan), selectedWeek);
  return (
    cleanText(currentDay?.countdown_label) ||
    cleanText(selectedWeek?.countdown_start) ||
    cleanText(selectedWeek?.countdown_end)
  );
}

function planPhase(plan: StructuredPlan | null, selectedWeek: StructuredWeek | null): string | null {
  return cleanText(selectedWeek?.phase_label) || cleanText(plan?.plan_metadata?.plan_type);
}

function eventDate(plan: PlanDetail, structuredPlan: StructuredPlan | null): string | null {
  return (
    formatEventDate(structuredPlan?.event_context?.fight_date) ||
    formatEventDate(structuredPlan?.event_context?.match_date) ||
    formatEventDate(plan.fight_date)
  );
}

function planSport(plan: PlanDetail, structuredPlan: StructuredPlan | null): string | null {
  return (
    cleanText(structuredPlan?.plan_metadata?.sport) ||
    cleanText(structuredPlan?.athlete_context?.sport_profile) ||
    cleanText(plan.technical_style?.join(", "))
  );
}

function supportMindsetRows(week: StructuredWeek | null): { label: string; value: string }[] {
  const rows: { label: string; value: string }[] = [];
  const seen = new Set<string>();
  const push = (label: string, value: string | null) => {
    if (!value) {
      return;
    }
    const key = `${label}:${value}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    rows.push({ label, value });
  };

  for (const day of getDays(week)) {
    const cardAnchor = day.today_card?.mindset_anchor;
    push("Intent", cleanText(cardAnchor?.intent));
    push("Focus", cleanText(cardAnchor?.focus_cue));
    push("Reset", cleanText(cardAnchor?.reset_cue));
    push("Anchor", cleanText(cardAnchor?.confidence_anchor));
    for (const session of getSessions(day)) {
      push("Intent", cleanText(session.mindset_anchor?.intent));
      push("Focus", cleanText(session.mindset_anchor?.focus_cue));
      push("Reset", cleanText(session.mindset_anchor?.reset_cue));
      push("Anchor", cleanText(session.mindset_anchor?.confidence_anchor));
      if (rows.length >= 6) {
        return rows;
      }
    }
    if (rows.length >= 6) {
      return rows;
    }
  }
  return rows;
}

function hasNutritionSupport(plan: StructuredPlan | null): boolean {
  return Boolean(
    plan &&
      (getDeterministicNutritionPhases(plan).length > 0 ||
        cleanText(plan.nutrition?.summary) ||
        cleanText(plan.nutrition?.daily_focus) ||
        cleanText(plan.nutrition?.training_day_guidance) ||
        cleanText(plan.nutrition?.fight_week_guidance) ||
        cleanText(plan.nutrition?.weight_cut_warning?.display_text)),
  );
}

function hasRecoverySupport(plan: StructuredPlan | null): boolean {
  return Boolean(plan && getDeterministicRecoveryPhases(plan).length > 0);
}

function SupportAccordion({
  eyebrow,
  title,
  defaultOpen = false,
  children,
}: {
  eyebrow: string;
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  return (
    <details className="camp-support-accordion" open={defaultOpen}>
      <summary className="camp-support-summary">
        <span>
          <span className="camp-eyebrow">{eyebrow}</span>
          <span className="camp-support-title">{title}</span>
        </span>
        <span className="camp-support-action">Open</span>
      </summary>
      <div className="camp-support-body">{children}</div>
    </details>
  );
}

function CommandHeader({
  plan,
  structuredPlan,
  selectedWeek,
  selectedWeekIndex,
  isActive,
  isArchived,
  canSetActive,
  setActivePending,
  activePlanError,
  planActionPending,
  canManagePlan,
  canPermanentlyDelete,
  onSetActive,
  onRename,
  onArchive,
  onPermanentDelete,
}: PlanCampMapProps & {
  selectedWeek: StructuredWeek | null;
  selectedWeekIndex: number;
}) {
  const phase = planPhase(structuredPlan, selectedWeek);
  const countdown = getCountdown(structuredPlan, selectedWeek);
  const fightDate = eventDate(plan, structuredPlan);
  const sport = planSport(plan, structuredPlan);
  const mainGoal = cleanText(selectedWeek?.week_goal) || cleanText(structuredPlan?.progression_notes);
  const statusText = isArchived ? "Archived" : isActive ? "ACTIVE" : titleize(plan.status || "Saved");

  return (
    <section className="camp-command">
      <div className="camp-command-copy">
        <p className="camp-eyebrow">Plan command</p>
        <div className="camp-title-row">
          <h1>{getPlanDisplayName(plan)}</h1>
          <span className={`camp-status-pill ${isActive ? "camp-status-active" : ""} ${isArchived ? "camp-status-archived" : ""}`.trim()}>
            {statusText}
          </span>
        </div>
        <div className="camp-command-meta">
          {sport ? <span>{sport}</span> : null}
          {phase ? <span>{titleize(phase)}</span> : null}
          <span>Week {selectedWeek ? weekNumber(selectedWeek, selectedWeekIndex) : "-"}</span>
          {countdown ? <span>{countdown}</span> : null}
          {fightDate ? <span>Fight date: {fightDate}</span> : null}
        </div>
        {mainGoal ? <p className="camp-command-goal">{mainGoal}</p> : null}
      </div>

      <div className="camp-command-actions">
        <Link href="/plans" className="ghost-button">
          Back to plans
        </Link>
        {isActive && !isArchived ? (
          <Link href="/today" className="cta">
            Open Today
          </Link>
        ) : null}
        {!isActive && !isArchived && canSetActive && !activePlanError ? (
          <button type="button" className="cta" onClick={onSetActive} disabled={setActivePending}>
            {setActivePending ? "Setting active..." : "Set Active"}
          </button>
        ) : null}
        {canManagePlan && !isArchived ? (
          <button type="button" className="ghost-button" onClick={onRename} disabled={planActionPending !== null}>
            {planActionPending === "rename" ? "Renaming..." : "Rename"}
          </button>
        ) : null}
        {canManagePlan && !isArchived ? (
          <button type="button" className="ghost-button" onClick={onArchive} disabled={planActionPending !== null}>
            {planActionPending === "archive" ? "Archiving..." : "Archive"}
          </button>
        ) : null}
        {canPermanentlyDelete && !isArchived ? (
          <button type="button" className="ghost-button danger-button" onClick={onPermanentDelete} disabled={planActionPending !== null}>
            {planActionPending === "permanent-delete" ? "Deleting..." : "Permanent delete"}
          </button>
        ) : null}
      </div>
    </section>
  );
}

function StateBanner({
  isActive,
  isArchived,
  canSetActive,
  activePlanError,
}: {
  isActive: boolean;
  isArchived: boolean;
  canSetActive: boolean;
  activePlanError?: string | null;
}) {
  if (isArchived) {
    return (
      <section className="camp-state-banner camp-state-archived">
        <strong>Archived plan.</strong>
        <span>View-only camp map. It will not drive Today until another plan is active.</span>
      </section>
    );
  }
  if (activePlanError) {
    return (
      <section className="camp-state-banner">
        <strong>Active state unavailable.</strong>
        <span>{activePlanError}</span>
      </section>
    );
  }
  if (isActive) {
    return (
      <section className="camp-state-banner camp-state-active">
        <strong>Active plan.</strong>
        <span>Today is reading from this camp.</span>
      </section>
    );
  }
  if (canSetActive) {
    return (
      <section className="camp-state-banner">
        <strong>Inactive plan.</strong>
        <span>Set it active when this is the camp that should drive Today.</span>
      </section>
    );
  }
  return (
    <section className="camp-state-banner">
      <strong>View only.</strong>
      <span>This plan is not eligible to become active from its current release state.</span>
    </section>
  );
}

function ReadinessStrip({
  plan,
  week,
  day,
}: {
  plan: StructuredPlan | null;
  week: StructuredWeek | null;
  day: StructuredDay | null;
}) {
  const session = firstSession(day);
  const readiness = cleanText(day?.today_card?.readiness_status) || "Use Today for check-in";
  const focus = cleanText(session?.objective) || sessionTitle(session, day) || "Review the selected week";
  const warning = getPrimaryWarning(plan, day) || "No structured risk note";
  const load = summarizeWeekLoad(week);

  return (
    <section className="camp-readiness-grid" aria-label="Readiness and risk context">
      <article className="camp-readiness-card">
        <span>Today call</span>
        <strong>{readiness}</strong>
      </article>
      <article className="camp-readiness-card">
        <span>Training focus</span>
        <strong>{focus}</strong>
      </article>
      <article className="camp-readiness-card camp-readiness-risk">
        <span>Injury watch</span>
        <strong>{warning}</strong>
      </article>
      <article className="camp-readiness-card">
        <span>Weekly load</span>
        <strong>{load}</strong>
      </article>
    </section>
  );
}

function WeekStrip({
  weeks,
  selectedWeekIndex,
  onSelectWeek,
}: {
  weeks: StructuredWeek[];
  selectedWeekIndex: number;
  onSelectWeek: (index: number) => void;
}) {
  if (!weeks.length) {
    return null;
  }
  const today = todayDate();
  return (
    <nav className="camp-week-strip" aria-label="Camp weeks">
      {weeks.map((week, index) => {
        const phase = cleanText(week.phase_label);
        const selected = index === selectedWeekIndex;
        const current = isTodayInWeek(week, today);
        return (
          <button
            key={cleanText(week.week_id) || `week-${index}`}
            type="button"
            className={`camp-week-pill ${selected ? "is-selected" : ""} ${current ? "is-current" : ""}`.trim()}
            onClick={() => onSelectWeek(index)}
          >
            <span>W{weekNumber(week, index)}</span>
            {phase ? <strong>{titleize(phase)}</strong> : null}
            <em>{summarizeWeekLoad(week)}</em>
            <small>{weekCompletionLabel(week)}</small>
          </button>
        );
      })}
    </nav>
  );
}

function WeekOverview({ week }: { week: StructuredWeek | null }) {
  if (!week) {
    return (
      <section className="camp-week-overview">
        <p className="camp-eyebrow">Selected week</p>
        <h2>No structured week found</h2>
        <p>Open the original plan text at the bottom for this saved plan.</p>
      </section>
    );
  }
  const phase = cleanText(week.phase_label);
  const goal = cleanText(week.week_goal);
  const warning = getDays(week)
    .map((day) => cleanText(day.today_card?.primary_warning) || cleanText(day.today_card?.weight_cut_warning))
    .find(Boolean);
  return (
    <section className="camp-week-overview">
      <p className="camp-eyebrow">Selected week</p>
      <div className="camp-week-overview-head">
        <h2>{weekLabel(week)}</h2>
        {phase ? <span className="camp-status-pill">{titleize(phase)}</span> : null}
      </div>
      <div className="camp-week-overview-grid">
        <article>
          <span>Goal</span>
          <strong>{goal || "No week goal supplied"}</strong>
        </article>
        <article>
          <span>Load</span>
          <strong>{summarizeWeekLoad(week)} intensity</strong>
        </article>
        <article>
          <span>Window</span>
          <strong>
            {[formatDateLabel(week.start_date), formatDateLabel(week.end_date)].filter(Boolean).join(" - ") ||
              "Dates not supplied"}
          </strong>
        </article>
        <article>
          <span>Main warning</span>
          <strong>{warning || "No primary warning"}</strong>
        </article>
      </div>
    </section>
  );
}

function SessionAccordion({
  session,
  day,
  defaultOpen,
}: {
  session: StructuredSession;
  day: StructuredDay;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(Boolean(defaultOpen));
  const title = sessionTitle(session, day);
  const objective = cleanText(session.objective);
  const duration = formatMeasured(session.planned_duration);
  const stressor = cleanText(session.primary_stressor) || cleanText(session.cns_demand);
  const impact = cleanText(session.impact_level);
  const status = cleanText(session.completion_status) || "Not started";
  const blocks = getBlocks(session);

  return (
    <details
      className="camp-session"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="camp-session-summary">
        <span>
          <strong>{title}</strong>
          {objective ? <em>{objective}</em> : null}
        </span>
        <span className="camp-session-meta">
          {duration ? <small>{duration}</small> : null}
          {stressor ? <small>{titleize(stressor)}</small> : null}
          {impact ? <small>{titleize(impact)}</small> : null}
          <small>{titleize(status)}</small>
        </span>
      </summary>
      <div className="camp-session-body">
        {cleanText(day.today_card?.primary_warning) ? (
          <p className="camp-risk-line">{cleanText(day.today_card?.primary_warning)}</p>
        ) : null}
        {blocks.length > 0 ? (
          <div className="camp-blocks">
            {blocks.map((block, index) => (
              <BlockCard key={cleanText(block.block_id) || `block-${index}`} block={block} />
            ))}
          </div>
        ) : (
          <p className="muted">No app blocks attached to this session.</p>
        )}
      </div>
    </details>
  );
}

function SessionlessDay({ day }: { day: StructuredDay }) {
  const view = classifySessionlessDay(day);
  return (
    <article className="camp-session camp-sessionless">
      <div className="camp-session-summary camp-sessionless-summary">
        <span>
          <strong>{view.title}</strong>
          {view.coachLed ? <em>Coach-owned work. Keep the plan context visible, but execute with the coach.</em> : null}
        </span>
        {view.tag ? <span className="camp-session-meta"><small>{view.tag}</small></span> : null}
      </div>
    </article>
  );
}

function DayCard({
  day,
  index,
  isCurrent,
  isOpen,
  onOpenChange,
}: {
  day: StructuredDay;
  index: number;
  isCurrent: boolean;
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const sessions = getSessions(day);
  const date = formatDateLabel(day.date);
  const countdown = cleanText(day.countdown_label);
  const dayType = cleanText(day.day_type);
  const warning = cleanText(day.today_card?.primary_warning) || cleanText(day.today_card?.weight_cut_warning);

  return (
    <details
      className={`camp-day-card ${isCurrent ? "is-current" : ""}`.trim()}
      open={isOpen}
      onToggle={(event) => onOpenChange(event.currentTarget.open)}
    >
      <summary className="camp-day-summary">
        <span className="camp-day-main">
          <span className="camp-day-kicker">
            {date || `Day ${index + 1}`}
            {countdown ? ` / ${countdown}` : ""}
          </span>
          <strong>{dayHeadline(day)}</strong>
          {warning ? <em>{warning}</em> : null}
        </span>
        <span className="camp-day-meta">
          {dayType ? <small>{titleize(dayType)}</small> : null}
          <small>{sessions.length} session{sessions.length === 1 ? "" : "s"}</small>
          <small>{completionLabel(sessions)}</small>
          {isCurrent ? <small className="camp-current-chip">Current day</small> : null}
        </span>
      </summary>
      <div className="camp-day-body">
        {sessions.length > 0 ? (
          sessions.map((session, sessionIndex) => (
            <SessionAccordion
              key={sessionKey(session, sessionIndex)}
              session={session}
              day={day}
              defaultOpen={sessionIndex === 0}
            />
          ))
        ) : (
          <SessionlessDay day={day} />
        )}
      </div>
    </details>
  );
}

function DayCards({
  week,
  openDayKey,
  onOpenDayKeyChange,
}: {
  week: StructuredWeek | null;
  openDayKey: string | null;
  onOpenDayKeyChange: (key: string | null) => void;
}) {
  const days = getDays(week);
  const today = todayDate();
  if (!days.length) {
    return (
      <section className="camp-day-list">
        <p className="muted">No days scheduled in this week.</p>
      </section>
    );
  }
  return (
    <section className="camp-day-list" aria-label="Week days and sessions">
      {days.map((day, index) => {
        const key = dayKey(day, index);
        return (
          <DayCard
            key={key}
            day={day}
            index={index}
            isCurrent={sameDay(parseDate(day.date), today)}
            isOpen={openDayKey === key}
            onOpenChange={(open) => {
              if (open) {
                onOpenDayKeyChange(key);
              } else if (openDayKey === key) {
                onOpenDayKeyChange(null);
              }
            }}
          />
        );
      })}
    </section>
  );
}

function SupportSections({
  plan,
  selectedWeek,
}: {
  plan: StructuredPlan | null;
  selectedWeek: StructuredWeek | null;
}) {
  if (!plan) {
    return null;
  }
  const mindsetRows = supportMindsetRows(selectedWeek);
  const progressionNotes = cleanText(plan.progression_notes);

  return (
    <section className="camp-support-stack" aria-label="Support notes">
      {hasRecoverySupport(plan) ? (
        <SupportAccordion eyebrow="Support" title="Recovery">
          <RecoveryCard plan={plan} />
        </SupportAccordion>
      ) : null}
      {hasNutritionSupport(plan) ? (
        <SupportAccordion eyebrow="Support" title="Nutrition">
          <NutritionCard plan={plan} />
        </SupportAccordion>
      ) : null}
      {mindsetRows.length > 0 ? (
        <SupportAccordion eyebrow="Support" title="Mindset">
          <ul className="camp-support-list">
            {mindsetRows.map((row, index) => (
              <li key={`${row.label}-${index}`}>
                <span>{row.label}</span>
                <strong>{row.value}</strong>
              </li>
            ))}
          </ul>
        </SupportAccordion>
      ) : null}
      {progressionNotes ? (
        <SupportAccordion eyebrow="Progression" title="Progression notes">
          <p className="camp-support-copy">{progressionNotes}</p>
        </SupportAccordion>
      ) : null}
    </section>
  );
}

function AdvisoryBanner({ advisory }: { advisory?: PlanAdvisory | null }) {
  if (!advisory) {
    return null;
  }
  return (
    <section className="camp-state-banner camp-state-risk">
      <strong>{advisory.title}</strong>
      <span>{advisory.suggestion || advisory.reason}</span>
    </section>
  );
}

function RawFallback({ rawText, structuredPlan }: { rawText: string; structuredPlan: StructuredPlan | null }) {
  const raw = cleanText(structuredPlan?.raw_markdown_fallback) || rawText.trim();
  if (!raw) {
    return null;
  }
  return (
    <details className="camp-raw-fallback">
      <summary>
        <span>Original Plan Text</span>
        <small>Fallback only</small>
      </summary>
      <pre>{raw}</pre>
    </details>
  );
}

export function PlanCampMap(props: PlanCampMapProps) {
  const { plan, structuredPlan, rawText, isActive, isArchived, canSetActive, activePlanError, primaryAdvisory } = props;
  const weeks = getWeeks(structuredPlan);
  const [selectedWeekIndex, setSelectedWeekIndex] = useState(0);
  const [openDayKey, setOpenDayKey] = useState<string | null>(null);

  useEffect(() => {
    const today = todayDate();
    const nextWeeks = getWeeks(structuredPlan);
    const nextWeekIndex = findInitialWeekIndex(nextWeeks, today);
    setSelectedWeekIndex(nextWeekIndex);
    setOpenDayKey(findDefaultDayKey(nextWeeks[nextWeekIndex], today));
  }, [structuredPlan]);

  const selectedWeek = weeks[selectedWeekIndex] || weeks[0] || null;
  const currentDay = getCurrentDay(weeks, selectedWeek);

  function handleSelectWeek(index: number) {
    const today = todayDate();
    setSelectedWeekIndex(index);
    setOpenDayKey(findDefaultDayKey(weeks[index], today));
  }

  return (
    <main className="camp-map">
      <CommandHeader {...props} selectedWeek={selectedWeek} selectedWeekIndex={selectedWeekIndex} />
      <StateBanner
        isActive={isActive}
        isArchived={isArchived}
        canSetActive={canSetActive}
        activePlanError={activePlanError}
      />
      <AdvisoryBanner advisory={primaryAdvisory} />
      <ReadinessStrip plan={structuredPlan} week={selectedWeek} day={currentDay} />
      {weeks.length > 0 ? (
        <>
          <WeekStrip weeks={weeks} selectedWeekIndex={selectedWeekIndex} onSelectWeek={handleSelectWeek} />
          <WeekOverview week={selectedWeek} />
          <DayCards week={selectedWeek} openDayKey={openDayKey} onOpenDayKeyChange={setOpenDayKey} />
          <SupportSections plan={structuredPlan} selectedWeek={selectedWeek} />
        </>
      ) : (
        <section className="camp-week-overview">
          <p className="camp-eyebrow">Structured map unavailable</p>
          <h2>This saved plan does not include week/day/session structure.</h2>
          <p>Use the original plan text below as a fallback for this older or malformed plan.</p>
        </section>
      )}
      <RawFallback rawText={rawText} structuredPlan={structuredPlan} />
    </main>
  );
}
