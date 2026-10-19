import { trainingDaysAgo } from "@/lib/history";
import { getPlanFreeGuidanceBanner, resolveTodayDecision } from "@/lib/today-authoritative";
import { EMPTY_TRAINING_HABITS, HABIT_WEEKDAYS, learnTrainingHabits, type TrainingHabitPreferences } from "@/lib/training-habits";
import { trainingLabel } from "@/lib/training-disciplines";
import { latestRepeatableTraining, sortTrainingHistory, type TrainingHistorySession } from "@/lib/training-history";
import { formatTrainingDuration, summarizeTraining, summaryWindowLoaded } from "@/lib/training-summary";
import type { TodayDecisionTone } from "@/lib/today";
import type { TodayCommandView } from "@/lib/types";

/**
 * Home for an athlete tracking their own coach's training (no UNLXCK plan).
 * Same cards as a plan athlete's Home; only their content comes from what the
 * athlete has, or has not, logged. Pure, so every state is unit-tested.
 */
export type TrackingHome = {
  hero: {
    eyebrow: string; title: string; lines: string[]; safety?: string; tone?: TodayDecisionTone;
    primary: { label: string; href: string };
  };
  strip: Array<{ label: string; value: string }>;
  /** What fills the fight-countdown slot: the first that has something to say. */
  slot: "summary" | "readiness" | "habits" | null;
  readiness?: { title: string; detail: string };
  routines: string[];
};

const LOG = "/today";

/** Completed training the summaries count: manual sessions and reported Unlxck completions. */
function counted(rows: readonly TrainingHistorySession[]): TrainingHistorySession[] {
  return rows.filter(row => row.status !== "skipped" && (row.source === "external" || row.completion_origin === "reported"));
}

function sessionLine(row: TrainingHistorySession): string {
  const name = row.source === "external" ? trainingLabel(row) : row.title;
  return [name, row.duration_minutes ? `${row.duration_minutes} min` : null].filter(Boolean).join(" · ");
}

function daysAgoLabel(day: string, today: string): string {
  const ago = trainingDaysAgo(day, today);
  return ago === 0 ? "Today" : ago === 1 ? "Yesterday" : ago === null ? "—" : `${ago} days ago`;
}

export function getTrackingHome({ state, rows, loadedFrom, today, canCheckIn, habits }: {
  state: TodayCommandView;
  /** History rows; null while loading or unavailable (nothing is claimed about them). */
  rows: readonly TrainingHistorySession[] | null;
  loadedFrom: string | null;
  today: string;
  /** Health-data consent: the daily check-in is offered only with it. */
  canCheckIn: boolean;
  habits?: TrainingHabitPreferences | null;
}): TrackingHome {
  const decision = resolveTodayDecision(state);
  const banner = getPlanFreeGuidanceBanner(state, decision);
  const checkedIn = state.today.recommendation_state !== "not_checked_in";
  const restricted = decision.primaryMessageKind === "safety_notice"
    || ["stop", "pull_back", "modify"].includes(decision.authoritativeTier);
  const done = rows ? sortTrainingHistory(counted(rows)) : null;
  const preferences = habits ?? EMPTY_TRAINING_HABITS;
  const routines = preferences.decisions.filter(item => item.state === "confirmed")
    .map(item => `${HABIT_WEEKDAYS[item.weekday]} · ${trainingLabel(item)} · ${item.duration_minutes} min`);

  let hero: TrackingHome["hero"];
  if (banner && restricted) {
    // Safety and restrictions lead exactly as on Today.
    hero = {
      eyebrow: decision.primaryMessageKind === "safety_notice" ? "Current safety" : "Today's guidance",
      title: banner.title, lines: [banner.detail, banner.action].filter((line): line is string => Boolean(line)),
      safety: banner.safety, tone: banner.tone === "neutral" ? undefined : banner.tone,
      primary: { label: "Open Today", href: "/today" },
    };
  } else if (!checkedIn && canCheckIn) {
    hero = {
      eyebrow: "Daily check-in", title: "How are you today?",
      lines: ["Sleep, body and pain — ten seconds, and today's guidance is ready."],
      primary: { label: "Check in", href: "/today#today-checkin" },
    };
  } else if (done && !done.length) {
    hero = {
      eyebrow: "Today", title: "Log your first session",
      lines: ["Your coach plans it. Log it here in seconds and UNLXCK tracks the rest."],
      primary: { label: "Log training", href: LOG },
    };
  } else {
    const readinessLine = checkedIn && banner ? `Check-in: ${banner.title.toLowerCase()}.` : null;
    const loggedToday = done?.filter(row => row.training_day === today) ?? [];
    const suggestion = done ? learnTrainingHabits(done.filter(row => row.source === "external"), today, preferences,
      { restricted: false, allowSparring: false }).suggestion : undefined;
    const last = done ? latestRepeatableTraining(done) ?? done[0] : undefined;
    if (loggedToday.length) {
      hero = {
        eyebrow: "Today", title: "Logged today",
        lines: [sessionLine(loggedToday[0]) + (loggedToday.length > 1 ? ` · +${loggedToday.length - 1} more` : "")],
        primary: { label: "Log another", href: LOG },
      };
    } else if (suggestion) {
      hero = {
        eyebrow: "Today", title: suggestion.title,
        lines: [`${trainingLabel(suggestion)} · ${suggestion.duration_minutes} min`],
        primary: { label: "Log it", href: LOG },
      };
    } else {
      hero = {
        eyebrow: "Today", title: "Log today's training",
        lines: last ? [`Last: ${sessionLine(last)} · ${daysAgoLabel(last.training_day, today).toLowerCase()}`] : [],
        primary: { label: "Log training", href: LOG },
      };
    }
    if (readinessLine) hero.lines.push(readinessLine);
  }

  // A rolling 7 training days, the same window as readiness and History, not a calendar week.
  const week = done && summaryWindowLoaded(loadedFrom, today, 7) ? summarizeTraining(done, today, 7) : null;
  const latest = done?.[0];
  const strip = [
    { label: "Last 7 days", value: week ? `${week.sessions} session${week.sessions === 1 ? "" : "s"}` : "—" },
    { label: "Time", value: week && week.minutes ? formatTrainingDuration(week.minutes) : "—" },
    { label: "Top discipline", value: week?.mix[0]?.label ?? "—" },
    { label: "Last session", value: latest ? daysAgoLabel(latest.training_day, today) : "—" },
  ];

  const recent = done ? summarizeTraining(done, today, 28).sessions > 0 : false;
  const readiness = checkedIn && banner && hero.title !== banner.title ? { title: banner.title, detail: banner.detail } : undefined;
  const slot = recent ? "summary" : readiness ? "readiness" : routines.length ? "habits" : null;
  return { hero, strip, slot, readiness, routines };
}
