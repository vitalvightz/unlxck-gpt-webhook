export type DaysOutContext = {
  daysOut: number | null;
  bucket: string;
  label: string;
  uiHints: {
    fight_proximity_banner: string | null;
  };
};

export function computeDaysUntilFight(fightDate: string | null | undefined): number | null {
  if (!fightDate) return null;
  const parsed = new Date(fightDate + "T00:00:00");
  if (Number.isNaN(parsed.getTime())) return null;
  const now = new Date();
  now.setHours(0, 0, 0, 0);
  const diffMs = parsed.getTime() - now.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  return diffDays < 0 ? null : diffDays;
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