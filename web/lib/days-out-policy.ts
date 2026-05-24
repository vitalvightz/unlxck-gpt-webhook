export type DaysOutContext = {
  daysOut: number | null;
  bucket: string;
  label: string;
  uiHints: {
    fight_proximity_banner: string | null;
  };
};

export type PerformanceFocusGroup = "key_goals" | "weak_areas";

export type PerformanceFocusOptionAvailability = {
  available: boolean;
  reason?: string;
};

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

export function buildDaysOutContext(daysUntilFight: number | null | undefined): DaysOutContext {
  return {
    daysOut: daysUntilFight ?? null,
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
