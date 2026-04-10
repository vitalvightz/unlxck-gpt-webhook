export type AvailabilityConsistency = {
  hardError: string | null;
  softWarning: string | null;
};

export type SparringConsistency = {
  hardError: string | null;
  softWarning: string | null;
};

export type HardSparringLoadWarning = {
  requiresConfirmation: boolean;
  warning: string | null;
};

function formatDayCountLabel(count: number): string {
  return `${count} day${count === 1 ? "" : "s"}`;
}

function formatSessionCountLabel(count: number): string {
  return `${count} weekly session${count === 1 ? "" : "s"}`;
}

export function getAvailabilityConsistency(
  trainingAvailability: string[],
  weeklyTrainingFrequency: number | null | undefined,
): AvailabilityConsistency {
  const availableDays = trainingAvailability.length;
  const sessionsPerWeek = weeklyTrainingFrequency ?? 0;
  const unusedDays = Math.max(availableDays - sessionsPerWeek, 0);

  if (!availableDays || !sessionsPerWeek) {
    return { hardError: null, softWarning: null };
  }

  if (sessionsPerWeek > availableDays) {
    return {
      hardError: `You selected ${formatDayCountLabel(availableDays)} available but planned ${formatSessionCountLabel(sessionsPerWeek)}.`,
      softWarning: null,
    };
  }

  if (unusedDays >= 3 && sessionsPerWeek <= 3) {
    return {
      hardError: null,
      softWarning: `You have ${formatDayCountLabel(availableDays)} available but only ${formatSessionCountLabel(sessionsPerWeek)}. That's fine if some days are optional.`,
    };
  }

  return { hardError: null, softWarning: null };
}

export function getSparringConsistency(
  trainingAvailability: string[],
  hardSparringDays: string[],
  technicalSkillDays: string[],
): SparringConsistency {
  const available = new Set(trainingAvailability);
  const invalidHard = hardSparringDays.filter((day) => !available.has(day));
  if (invalidHard.length) {
    return {
      hardError: `Hard sparring days must also be selected as available days: ${invalidHard.join(", ")}.`,
      softWarning: null,
    };
  }

  const invalidTechnical = technicalSkillDays.filter((day) => !available.has(day));
  if (invalidTechnical.length) {
    return {
      hardError: `Technical / lighter skill days must also be selected as available days: ${invalidTechnical.join(", ")}.`,
      softWarning: null,
    };
  }

  const overlap = hardSparringDays.filter((day) => technicalSkillDays.includes(day));
  if (overlap.length) {
    return {
      hardError: `A day cannot be both hard sparring and technical / lighter skill: ${overlap.join(", ")}.`,
      softWarning: null,
    };
  }

  if (!hardSparringDays.length && technicalSkillDays.length) {
    return {
      hardError: null,
      softWarning: "Technical / lighter skill days are set, but hard sparring days are blank. That's fine if sparring is light or not fixed yet.",
    };
  }

  return { hardError: null, softWarning: null };
}

export function getHardSparringLoadWarning(
  hardSparringDays: string[],
  weeklyTrainingFrequency: number | null | undefined,
): HardSparringLoadWarning {
  const hardDayCount = hardSparringDays.length;
  if (hardDayCount < 3) {
    return { requiresConfirmation: false, warning: null };
  }

  const sessionsPerWeek = weeklyTrainingFrequency ?? null;
  if (!sessionsPerWeek) {
    return {
      requiresConfirmation: true,
      warning: `You marked ${hardDayCount} hard sparring days before planned weekly sessions are set. That's already a heavy collision load. Are you sure you want to keep that many hard days locked in?`,
    };
  }

  let densityDetail = "That's a heavy amount of hard contact for one week.";
  if (hardDayCount > sessionsPerWeek) {
    densityDetail = "That is more hard sparring days than total planned sessions in the week.";
  } else if (hardDayCount === sessionsPerWeek) {
    densityDetail = "That would make every planned session a hard sparring session.";
  } else if (sessionsPerWeek - hardDayCount === 1) {
    densityDetail = "That leaves only one planned session not marked as hard sparring.";
  }

  return {
    requiresConfirmation: true,
    warning: `You marked ${hardDayCount} hard sparring days inside ${sessionsPerWeek} planned weekly sessions. ${densityDetail} Are you sure you want to keep that many hard days locked in?`,
  };
}

export function getHardSparringWarningContextKey(
  hardSparringDays: string[],
  weeklyTrainingFrequency: number | null | undefined,
): string {
  const orderedDays = Array.from(new Set(hardSparringDays)).sort();
  return `${orderedDays.join("|")}::${weeklyTrainingFrequency ?? ""}`;
}
