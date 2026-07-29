export type DaysOutContext = {
  daysOut: number | null;
  hasHardSparring: boolean;
  bucket: string;
  label: string;
  uiHints: {
    fight_proximity_banner: string | null;
  };
};

export type BuildDaysOutContextOptions = {
  hasHardSparring?: boolean;
};

export type PerformanceFocusGroup = "key_goals" | "weak_areas";

export type PerformanceFocusOptionAvailability = {
  available: boolean;
  reason?: string;
};

export const HARD_SPARRING_STRENGTH_BLOCK_REASON =
  "Strength is blocked this close to fight day because hard sparring is selected. The plan will preserve freshness and use primers/support work instead.";

export const HARD_SPARRING_STRENGTH_REMOVAL_MESSAGE =
  "Strength was removed because hard sparring is selected this close to fight day. The plan will preserve freshness and use primers/support work instead.";

export function computeDaysUntilFight(
  fightDate: string | null | undefined,
  nowInput?: Date,
): number | null {
  if (!fightDate) return null;
  const parsed = new Date(fightDate + "T00:00:00");
  if (Number.isNaN(parsed.getTime())) return null;
  const now = nowInput ? new Date(nowInput) : new Date();
  now.setHours(0, 0, 0, 0);
  const diffMs = parsed.getTime() - now.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  return diffDays < 0 ? null : diffDays;
}

export const FIGHT_WEEK_LOCK_THRESHOLD_DAYS = 7;

/**
 * Return the weekday that must be locked out of the combat-load tag pickers,
 * or null when no lock applies.
 *
 * The fight weekday is only locked inside fight week, where it occurs exactly
 * once and that occurrence is the fight itself. At 7+ days out the same weekday
 * recurs on ordinary training days, and the backend fight-day override
 * (fightcamp/fight_day_override.py) already clamps the real fight day on the
 * final camp week.
 */
export function getFightDayLockedWeekday(
  fightDateWeekday: string | null | undefined,
  daysUntilFight: number | null | undefined,
): string | null {
  if (!fightDateWeekday) return null;
  // null covers "no fight date" and "fight date already passed".
  if (daysUntilFight === null || daysUntilFight === undefined) return null;
  if (daysUntilFight >= FIGHT_WEEK_LOCK_THRESHOLD_DAYS) return null;
  return fightDateWeekday;
}

export function isFightDateInPast(
  fightDate: string | null | undefined,
  nowInput?: Date,
): boolean {
  if (!fightDate) return false;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(fightDate)) return false;
  const [year, month, day] = fightDate.split("-").map(Number);
  const parsedDate = new Date(Date.UTC(year, month - 1, day));
  if (Number.isNaN(parsedDate.getTime())) return false;
  const now = nowInput ? new Date(nowInput) : new Date();
  const nowDate = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
  return parsedDate.getTime() < nowDate.getTime();
}

const KEY_GOAL_BLOCK_REASONS: Record<string, string> = {
  power: "Too late for power development.",
  strength: "Too late for strength development.",
  conditioning: "Too late to build conditioning safely.",
  speed: "Fight-week freshness only.",
  skill_refinement: "Fight-week freshness only.",
};

const WEAK_AREA_BLOCK_REASONS: Record<string, string> = {
  gas_tank: "Too late to build gas tank safely.",
  strength: "Too late for strength development.",
  power: "Too late for power development.",
  speed: "Fight-week freshness only.",
  footwork: "Fight-week freshness only.",
  trunk_strength: "Too close to fight day.",
};

function getBlockedPerformanceFocusValues(group: PerformanceFocusGroup, daysOut: number): Set<string> {
  if (daysOut >= 14) {
    return new Set();
  }

  if (group === "key_goals") {
    if (daysOut >= 8) {
      return new Set(["strength", "conditioning"]);
    }
    if (daysOut >= 5) {
      return new Set(["power", "strength", "conditioning"]);
    }
    if (daysOut >= 2) {
      return new Set(["power", "strength", "conditioning", "speed"]);
    }
    return new Set(["power", "strength", "conditioning", "speed", "skill_refinement"]);
  }

  if (daysOut >= 8) {
    return new Set(["gas_tank", "strength"]);
  }
  if (daysOut >= 5) {
    return new Set(["gas_tank", "strength", "power"]);
  }
  if (daysOut >= 2) {
    return new Set(["gas_tank", "strength", "power", "speed", "trunk_strength"]);
  }
  return new Set(["gas_tank", "strength", "power", "speed", "footwork", "trunk_strength"]);
}

export function getPerformanceFocusOptionAvailability(
  ctx: DaysOutContext,
  group: PerformanceFocusGroup,
  value: string,
): PerformanceFocusOptionAvailability {
  if (ctx.daysOut === null) {
    return { available: true };
  }

  const normalizedValue = value.trim().toLowerCase();
  if (
    normalizedValue === "strength" &&
    ctx.hasHardSparring &&
    ctx.daysOut !== null &&
    ctx.daysOut <= 20
  ) {
    return {
      available: false,
      reason: HARD_SPARRING_STRENGTH_BLOCK_REASON,
    };
  }

  if (!getBlockedPerformanceFocusValues(group, ctx.daysOut).has(normalizedValue)) {
    return { available: true };
  }

  const reasonMap = group === "key_goals" ? KEY_GOAL_BLOCK_REASONS : WEAK_AREA_BLOCK_REASONS;
  return {
    available: false,
    reason: reasonMap[normalizedValue] ?? "Too close to fight day.",
  };
}

export function filterAvailablePerformanceFocusValues(
  ctx: DaysOutContext,
  group: PerformanceFocusGroup,
  values: string[],
): string[] {
  return values.filter((value) => getPerformanceFocusOptionAvailability(ctx, group, value).available);
}

export function buildDaysOutContext(
  daysUntilFight: number | null | undefined,
  options: BuildDaysOutContextOptions = {},
): DaysOutContext {
  return {
    daysOut: daysUntilFight ?? null,
    hasHardSparring: Boolean(options.hasHardSparring),
    bucket: "CAMP",
    label: "Camp",
    uiHints: {
      fight_proximity_banner: null,
    },
  };
}

export function shouldHideField(_ctx: DaysOutContext, _fieldName: string): boolean {
  return false;
}

export function shouldDisableField(_ctx: DaysOutContext, _fieldName: string): boolean {
  return false;
}

export function shouldDeEmphasizeField(_ctx: DaysOutContext, _fieldName: string): boolean {
  return false;
}

export function getFieldHelperText(_ctx: DaysOutContext, _fieldName: string): string | undefined {
  return undefined;
}
