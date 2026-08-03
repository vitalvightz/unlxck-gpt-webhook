import {
  XP_ACTIONS,
  createFreshXpState,
  type XpAction,
  type XpAwardRecord,
  type XpState,
} from "@/lib/xp";

export type XpOpportunity = {
  code: string;
  label: string;
  xp: number;
  href: string;
  priority: number;
};

export type XpWeekProgress = {
  planId: string;
  weekId: string;
  weekIndex: number | null;
  phaseLabel: string;
  startDate: string;
  endDate: string;
  completedSessions: number;
  plannedSessions: number;
  remainingSessions: number;
  complete: boolean;
  weekXpEarned: boolean;
};

export type XpMilestone = {
  id: string;
  planId: string;
  milestoneType: "phase_completed" | "plan_completed" | "camp_completed";
  phaseLabel: string | null;
  completedAt: string;
  displayLabel: string;
};

export type XpProgress = {
  state: XpState;
  opportunities: XpOpportunity[];
  currentWeek: XpWeekProgress | null;
  majorMilestones: XpMilestone[];
};

const actionNames = new Set(Object.keys(XP_ACTIONS));
const milestoneTypes = new Set(["phase_completed", "plan_completed", "camp_completed"]);

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function nonNegativeInteger(value: unknown): number | null {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0
    ? value
    : null;
}

function validDateTime(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0 && Number.isFinite(Date.parse(value));
}

function parseAward(value: unknown): XpAwardRecord | null {
  const candidate = record(value);
  if (!candidate) return null;
  const action = candidate.action;
  const amount = nonNegativeInteger(candidate.amount);
  if (
    typeof candidate.id !== "string" ||
    !candidate.id.trim() ||
    typeof action !== "string" ||
    !actionNames.has(action) ||
    amount === null ||
    amount !== XP_ACTIONS[action as XpAction].xp ||
    !validDateTime(candidate.awarded_at)
  ) {
    return null;
  }
  const calendarDate =
    typeof candidate.calendar_date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(candidate.calendar_date)
      ? candidate.calendar_date
      : undefined;
  return {
    id: candidate.id.trim(),
    action: action as XpAction,
    amount,
    awardedAt: new Date(candidate.awarded_at).toISOString(),
    ...(calendarDate ? { calendarDate } : {}),
  };
}

function parseState(value: unknown): XpState {
  const candidate = record(value);
  if (!candidate) throw new Error("Server returned invalid XP progress.");
  const totalXp = nonNegativeInteger(candidate.total_xp);
  const awards = Array.isArray(candidate.recent_awards)
    ? candidate.recent_awards.map(parseAward)
    : [];
  if (
    totalXp === null ||
    !Array.isArray(candidate.recent_awards) ||
    awards.some((award) => award === null) ||
    awards.length > 20
  ) {
    throw new Error("Server returned invalid XP progress.");
  }
  const lastDailyLoginDate =
    candidate.last_daily_login_date === null || candidate.last_daily_login_date === undefined
      ? null
      : typeof candidate.last_daily_login_date === "string" &&
          /^\d{4}-\d{2}-\d{2}$/.test(candidate.last_daily_login_date)
        ? candidate.last_daily_login_date
        : undefined;
  if (lastDailyLoginDate === undefined) {
    throw new Error("Server returned invalid XP progress.");
  }
  return {
    ...createFreshXpState(),
    totalXp,
    lastDailyLoginDate,
    recentAwards: awards as XpAwardRecord[],
  };
}

function parseOpportunity(value: unknown): XpOpportunity | null {
  const candidate = record(value);
  if (!candidate) return null;
  const xp = nonNegativeInteger(candidate.xp);
  const priority = nonNegativeInteger(candidate.priority);
  if (
    typeof candidate.code !== "string" ||
    !candidate.code.trim() ||
    typeof candidate.label !== "string" ||
    !candidate.label.trim() ||
    typeof candidate.href !== "string" ||
    !candidate.href.startsWith("/") ||
    xp === null ||
    xp <= 0 ||
    priority === null
  ) {
    return null;
  }
  return {
    code: candidate.code.trim(),
    label: candidate.label.trim(),
    href: candidate.href,
    xp,
    priority,
  };
}

function parseWeek(value: unknown): XpWeekProgress | null {
  if (value === null || value === undefined) return null;
  const candidate = record(value);
  if (!candidate) throw new Error("Server returned invalid XP week progress.");
  const completedSessions = nonNegativeInteger(candidate.completed_sessions);
  const plannedSessions = nonNegativeInteger(candidate.planned_sessions);
  const remainingSessions = nonNegativeInteger(candidate.remaining_sessions);
  const rawWeekIndex = candidate.week_index;
  const weekIndex = rawWeekIndex === null || rawWeekIndex === undefined
    ? null
    : nonNegativeInteger(rawWeekIndex);
  if (
    typeof candidate.plan_id !== "string" ||
    !candidate.plan_id.trim() ||
    typeof candidate.week_id !== "string" ||
    !candidate.week_id.trim() ||
    typeof candidate.phase_label !== "string" ||
    typeof candidate.start_date !== "string" ||
    typeof candidate.end_date !== "string" ||
    completedSessions === null ||
    plannedSessions === null ||
    remainingSessions === null ||
    (rawWeekIndex !== null && rawWeekIndex !== undefined && weekIndex === null) ||
    typeof candidate.complete !== "boolean" ||
    typeof candidate.week_xp_earned !== "boolean" ||
    completedSessions > plannedSessions ||
    remainingSessions !== plannedSessions - completedSessions
  ) {
    throw new Error("Server returned invalid XP week progress.");
  }
  return {
    planId: candidate.plan_id.trim(),
    weekId: candidate.week_id.trim(),
    weekIndex,
    phaseLabel: candidate.phase_label.trim(),
    startDate: candidate.start_date,
    endDate: candidate.end_date,
    completedSessions,
    plannedSessions,
    remainingSessions,
    complete: candidate.complete,
    weekXpEarned: candidate.week_xp_earned,
  };
}

function parseMilestone(value: unknown): XpMilestone | null {
  const candidate = record(value);
  if (!candidate) return null;
  const milestoneType = candidate.milestone_type;
  if (
    typeof candidate.id !== "string" ||
    typeof candidate.plan_id !== "string" ||
    typeof milestoneType !== "string" ||
    !milestoneTypes.has(milestoneType) ||
    !validDateTime(candidate.completed_at) ||
    typeof candidate.display_label !== "string" ||
    !candidate.display_label.trim() ||
    !(
      candidate.phase_label === null ||
      candidate.phase_label === undefined ||
      typeof candidate.phase_label === "string"
    )
  ) {
    return null;
  }
  return {
    id: candidate.id,
    planId: candidate.plan_id,
    milestoneType: milestoneType as XpMilestone["milestoneType"],
    phaseLabel: typeof candidate.phase_label === "string" ? candidate.phase_label : null,
    completedAt: new Date(candidate.completed_at).toISOString(),
    displayLabel: candidate.display_label.trim(),
  };
}

export function createFreshXpProgress(): XpProgress {
  return {
    state: createFreshXpState(),
    opportunities: [],
    currentWeek: null,
    majorMilestones: [],
  };
}

export function parseXpProgressResponse(value: unknown): XpProgress {
  const candidate = record(value);
  if (!candidate) throw new Error("Server returned invalid XP progress.");
  const opportunities = Array.isArray(candidate.opportunities)
    ? candidate.opportunities.map(parseOpportunity)
    : [];
  const milestones = Array.isArray(candidate.major_milestones)
    ? candidate.major_milestones.map(parseMilestone)
    : [];
  if (
    !Array.isArray(candidate.opportunities) ||
    opportunities.some((item) => item === null) ||
    opportunities.length > 3 ||
    !Array.isArray(candidate.major_milestones) ||
    milestones.some((item) => item === null) ||
    milestones.length > 50
  ) {
    throw new Error("Server returned invalid XP progress.");
  }
  return {
    state: parseState(candidate.state),
    opportunities: opportunities as XpOpportunity[],
    currentWeek: parseWeek(candidate.current_week),
    majorMilestones: milestones as XpMilestone[],
  };
}
