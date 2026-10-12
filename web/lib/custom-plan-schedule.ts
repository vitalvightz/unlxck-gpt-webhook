import type { CustomSession } from "./api-schema.generated";
import type { MeResponse } from "./types";
import { hydratePlanRequest } from "./onboarding";

const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] as const;
type Schedule = { session_types_by_day?: Record<string, string> };

/** Seed a new draft once. Support slots alone never declare skill work. */
export function customSchedulePrefill(me: MeResponse | null): CustomSession[] {
  const intake = hydratePlanRequest(me);
  const draft = me?.profile.onboarding_draft as Schedule | null | undefined;
  const latest = me?.latest_intake as (Schedule & object) | null | undefined;
  const types = draft?.session_types_by_day ?? latest?.session_types_by_day ?? {};
  const sameDay = (a: string, b: string) => a.toLowerCase().slice(0, 3) === b.toLowerCase().slice(0, 3);
  return weekdays.flatMap((weekday) => {
    const hard = intake.hard_sparring_days.some((day) => sameDay(day, weekday))
      || Object.entries(types).some(([day, type]) => sameDay(day, weekday) && type === "hard_spar");
    const technical = Object.entries(types).some(([day, type]) => sameDay(day, weekday) && type === "technical");
    return [
      ...(hard ? [{ name: "Hard sparring", session_type: "sparring" as const }] : []),
      ...(technical ? [{ name: "Light technical / skill", session_type: "skill" as const }] : []),
    ].map((session) => ({ ...session, id: crypto.randomUUID(), weekday, exercises: [] }));
  });
}
