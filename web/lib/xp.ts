export type XpAction =
  | "daily_login"
  | "training_logged"
  | "planned_session_completed"
  | "recommended_fighter_content_watched"
  | "full_training_week_completed";

export type XpActionConfig = {
  label: string;
  xp: number;
};

export type XpLevelConfig = {
  level: number;
  title: string;
  threshold: number;
};

export type XpAwardRecord = {
  id: string;
  action: XpAction;
  amount: number;
  awardedAt: string;
  calendarDate?: string;
};

export type XpState = {
  totalXp: number;
  lastDailyLoginDate: string | null;
  recentAwards: XpAwardRecord[];
};

export type XpAwardResult = {
  state: XpState;
  previousTotalXp: number;
  awarded: boolean;
  award: XpAwardRecord | null;
};

export type XpLevelProgress = {
  totalXp: number;
  currentLevel: XpLevelConfig;
  nextLevel: XpLevelConfig | null;
  percentage: number;
  xpWithinLevel: number;
  xpForNextLevel: number;
  xpRemaining: number;
};

export const XP_RECENT_AWARDS_LIMIT = 20;

export const XP_ACTIONS: Record<XpAction, XpActionConfig> = {
  daily_login: { label: "Daily login", xp: 10 },
  training_logged: { label: "Training logged", xp: 25 },
  planned_session_completed: { label: "Planned session completed", xp: 50 },
  recommended_fighter_content_watched: { label: "Recommended fighter content watched", xp: 10 },
  full_training_week_completed: { label: "Full training week completed", xp: 100 },
};

export const XP_LEVELS: readonly XpLevelConfig[] = [
  { level: 1, title: "Rookie", threshold: 0 },
  { level: 2, title: "Prospect", threshold: 100 },
  { level: 3, title: "Amateur", threshold: 250 },
  { level: 4, title: "Challenger", threshold: 450 },
  { level: 5, title: "Ranked", threshold: 700 },
  { level: 6, title: "Contender", threshold: 1_000 },
  { level: 7, title: "Elite", threshold: 1_300 },
  { level: 8, title: "Champion", threshold: 1_700 },
] as const;

const XP_ACTION_NAMES = new Set<XpAction>(Object.keys(XP_ACTIONS) as XpAction[]);

function sanitizeTotalXp(value: unknown): number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : 0;
}

function isValidCalendarDate(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false;
  }
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

function isXpAction(value: unknown): value is XpAction {
  return typeof value === "string" && XP_ACTION_NAMES.has(value as XpAction);
}

function parseApiAward(value: unknown): XpAwardRecord | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const candidate = value as Record<string, unknown>;
  const action = candidate.action;
  const awardedAt = candidate.awarded_at;
  if (
    typeof candidate.id !== "string" ||
    !candidate.id.trim() ||
    !isXpAction(action) ||
    candidate.amount !== XP_ACTIONS[action].xp ||
    typeof awardedAt !== "string" ||
    !Number.isFinite(Date.parse(awardedAt))
  ) {
    return null;
  }

  const calendarDate = isValidCalendarDate(candidate.calendar_date)
    ? candidate.calendar_date
    : undefined;
  return {
    id: candidate.id.trim(),
    action,
    amount: XP_ACTIONS[action].xp,
    awardedAt: new Date(awardedAt).toISOString(),
    ...(calendarDate ? { calendarDate } : {}),
  };
}

export function createFreshXpState(): XpState {
  return {
    totalXp: 0,
    lastDailyLoginDate: null,
    recentAwards: [],
  };
}

/** Convert and validate the server response before it reaches presentation. */
export function parseXpAwardResponse(value: unknown): XpAwardResult {
  if (!value || typeof value !== "object") {
    throw new Error("Server returned invalid XP data.");
  }
  const candidate = value as Record<string, unknown>;
  const rawState = candidate.state;
  if (!rawState || typeof rawState !== "object") {
    throw new Error("Server returned invalid XP data.");
  }
  const stateCandidate = rawState as Record<string, unknown>;
  const totalXp = sanitizeTotalXp(stateCandidate.total_xp);
  const previousTotalXp = sanitizeTotalXp(candidate.previous_total_xp);
  const recentAwards = Array.isArray(stateCandidate.recent_awards)
    ? stateCandidate.recent_awards.map(parseApiAward).filter((award): award is XpAwardRecord => award !== null)
    : [];
  const award = candidate.award === null ? null : parseApiAward(candidate.award);

  if (
    typeof candidate.awarded !== "boolean" ||
    totalXp !== stateCandidate.total_xp ||
    previousTotalXp !== candidate.previous_total_xp ||
    !Array.isArray(stateCandidate.recent_awards) ||
    recentAwards.length !== stateCandidate.recent_awards.length ||
    recentAwards.length > XP_RECENT_AWARDS_LIMIT ||
    (candidate.awarded && !award) ||
    (!candidate.awarded && candidate.award !== null)
  ) {
    throw new Error("Server returned invalid XP data.");
  }

  const lastDailyLoginDate = isValidCalendarDate(stateCandidate.last_daily_login_date)
    ? stateCandidate.last_daily_login_date
    : null;
  if (stateCandidate.last_daily_login_date !== null && lastDailyLoginDate === null) {
    throw new Error("Server returned invalid XP data.");
  }

  return {
    state: {
      totalXp,
      lastDailyLoginDate,
      recentAwards,
    },
    previousTotalXp,
    awarded: candidate.awarded,
    award,
  };
}

export function resolveXpLevel(totalXpInput: unknown): XpLevelProgress {
  const totalXp = sanitizeTotalXp(totalXpInput);
  let currentIndex = 0;
  for (let index = 1; index < XP_LEVELS.length; index += 1) {
    if (totalXp < XP_LEVELS[index].threshold) {
      break;
    }
    currentIndex = index;
  }

  const currentLevel = XP_LEVELS[currentIndex];
  const nextLevel = XP_LEVELS[currentIndex + 1] ?? null;
  if (!nextLevel) {
    return {
      totalXp,
      currentLevel,
      nextLevel: null,
      percentage: 100,
      xpWithinLevel: Math.max(0, totalXp - currentLevel.threshold),
      xpForNextLevel: 0,
      xpRemaining: 0,
    };
  }

  const xpWithinLevel = totalXp - currentLevel.threshold;
  const xpForNextLevel = nextLevel.threshold - currentLevel.threshold;
  const xpRemaining = Math.max(0, nextLevel.threshold - totalXp);
  return {
    totalXp,
    currentLevel,
    nextLevel,
    percentage: Math.max(0, Math.min(100, (xpWithinLevel / xpForNextLevel) * 100)),
    xpWithinLevel,
    xpForNextLevel,
    xpRemaining,
  };
}
