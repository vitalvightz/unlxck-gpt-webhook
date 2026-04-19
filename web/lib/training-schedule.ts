export type AvailabilityConsistency = {
  hardError: string | null;
  softWarning: string | null;
};

export type SparringConsistency = {
  hardError: string | null;
  softWarning: string | null;
};

export type HardSparringWarning = {
  acknowledgementContextKey: string;
  message: string | null;
  requiresAcknowledgement: boolean;
};

function getSortedUniqueDays(days: string[]): string[] {
  return [...new Set(days)].sort((left, right) => left.localeCompare(right));
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
      hardError: `You selected ${availableDays} available day${availableDays === 1 ? "" : "s"} but planned ${sessionsPerWeek} weekly session${sessionsPerWeek === 1 ? "" : "s"}.`,
      softWarning: null,
    };
  }

  if (unusedDays >= 3 && sessionsPerWeek <= 3) {
    return {
      hardError: null,
      softWarning: `You have ${availableDays} days available but only ${sessionsPerWeek} planned weekly session${sessionsPerWeek === 1 ? "" : "s"}. That's fine if some days are optional.`,
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

export function getHardSparringWarning(
  hardSparringDays: string[],
  weeklyTrainingFrequency: number | null | undefined,
): HardSparringWarning {
  const normalizedHardSparringDays = getSortedUniqueDays(hardSparringDays);
  const sessionsPerWeek = weeklyTrainingFrequency ?? 0;
  const acknowledgementContextKey = `hard-sparring:${sessionsPerWeek}:${normalizedHardSparringDays.join("|")}`;

  if (normalizedHardSparringDays.length < 3) {
    return {
      acknowledgementContextKey,
      message: null,
      requiresAcknowledgement: false,
    };
  }

  const sessionLabel = sessionsPerWeek
    ? `${sessionsPerWeek} planned weekly session${sessionsPerWeek === 1 ? "" : "s"}`
    : "the current weekly session plan";

  return {
    acknowledgementContextKey,
    message: `You selected ${normalizedHardSparringDays.length} hard sparring days inside ${sessionLabel}. That's a high contact load, so confirm the athlete can recover from it before continuing.`,
    requiresAcknowledgement: true,
  };
}
