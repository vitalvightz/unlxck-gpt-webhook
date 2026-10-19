import { athleteTrainingDayISO } from "./camp-map";
import { canRepeatTraining, type TrainingActivity, type TrainingHistorySession } from "./training-history";
import type { TrainingClassification, TrainingSessionType, TrainingSport } from "./training-disciplines";

export const HABIT_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] as const;
export type TrainingHabitDecision = {
  weekday: number;
  activity: TrainingActivity;
  /** Absent on routines saved before sport and session type existed. */
  sport?: TrainingSport | null;
  session_type?: TrainingSessionType | null;
  duration_minutes: number;
  state: "confirmed" | "dismissed";
  decided_on: string;
};
export type TrainingHabitPreferences = { enabled: boolean; decisions: TrainingHabitDecision[] };
export const EMPTY_TRAINING_HABITS: TrainingHabitPreferences = { enabled: true, decisions: [] };
type Candidate = {
  activity: TrainingActivity; sport?: TrainingSport | null; session_type?: TrainingSessionType | null;
  duration_minutes: number; dates: string[]; score: number;
  source: TrainingHistorySession; repeated: boolean;
};
export type HabitSuggestion = {
  activity: TrainingActivity; sport?: TrainingSport | null; session_type?: TrainingSessionType | null;
  duration_minutes: number; title: string; source?: TrainingHistorySession;
};
/**
 * One habit is one exact kind of session: activity, sport and session type.
 * BJJ rolling and Muay Thai clinch never merge into one "Other" habit; older
 * records and routines without a sport keep matching each other.
 */
export function habitKey(row: TrainingClassification): string {
  return `${row.activity}|${row.sport ?? ""}|${row.session_type ?? ""}`;
}
export type HabitPrompt = Candidate & { weekday: number; replace?: TrainingHabitDecision };
/** Match the API's UTC fallback, including blank/unknown profile timezones. */
export function habitTrainingDay(now: Date, timezone: string | null | undefined): string {
  let zone = timezone?.trim() || "UTC";
  try { new Intl.DateTimeFormat("en", { timeZone: zone }); }
  catch { zone = "UTC"; }
  return athleteTrainingDayISO(now, zone);
}

const dayNumber = (day: string) => {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return NaN;
  const value = Date.parse(`${day}T12:00:00Z`);
  return Number.isFinite(value) && new Date(value).toISOString().slice(0, 10) === day ? Math.floor(value / 86400000) : NaN;
};
export const habitWeekday = (day: string) => ((dayNumber(day) + 3) % 7 + 7) % 7;
const median = (values: number[]) => {
  const sorted = [...values].sort((a, b) => a - b);
  return Math.round((sorted[Math.floor((sorted.length - 1) / 2)] + sorted[Math.floor(sorted.length / 2)]) / 2);
};

/** Forty-two local calendar days; each activity/day is one observation, regardless of entry count. */
export function learnTrainingHabits(rows: TrainingHistorySession[], today: string, preferences = EMPTY_TRAINING_HABITS,
  options: { coachScheduled?: boolean; restricted?: boolean; allowSparring?: boolean; truncated?: boolean; historyUnavailable?: boolean } = {}) {
  const weekday = habitWeekday(today);
  const none = { weekday, suggestion: undefined as HabitSuggestion | undefined, prompt: undefined as HabitPrompt | undefined };
  if (!preferences.enabled || !Number.isFinite(weekday) || options.coachScheduled || options.restricted) return none;
  const age = (day: string) => dayNumber(today) - dayNumber(day);
  const seen = new Set<string>();
  const history = rows.filter(row => {
    if (!canRepeatTraining(row) || age(row.training_day) < 0 || age(row.training_day) > 41 || seen.has(row.id)) return false;
    seen.add(row.id); return Number.isFinite(age(row.training_day));
  });
  const current = history.filter(row => habitWeekday(row.training_day) === weekday);
  const decisions = preferences.decisions.filter(item => item.weekday === weekday);
  const confirmed = decisions.filter(item => item.state === "confirmed");
  // Confirmed preferences survive unavailable/incomplete evidence. Only inference pauses.
  const canLearn = !options.historyUnavailable && !options.truncated;
  const groups = new Map<string, TrainingHistorySession[]>();
  for (const row of canLearn ? current : []) {
    if (row.activity === "sparring" && !options.allowSparring) continue;
    const key = habitKey(row);
    if (decisions.some(item => habitKey(item) === key && item.state === "dismissed")) continue;
    const list = groups.get(key) ?? []; list.push(row); groups.set(key, list);
  }
  // Consistency leads: recency-weighted weekday frequency, then latest date, then kind.
  const candidates: (Candidate & { key: string })[] = [...groups].map(([key, list]) => {
    const dates = [...new Set(list.map(row => row.training_day))].sort().reverse();
    // A day with several entries has the same weight as a day with one entry.
    const dailyMinutes = dates.slice(0, 3).map(day => median(list.filter(row => row.training_day === day).map(row => row.duration_minutes!)));
    const source = list.find(row => row.training_day === dates[0])!;
    const { sport, session_type } = source;
    return { key, activity: source.activity!, ...(sport ? { sport, session_type: session_type ?? null } : {}),
      dates, duration_minutes: median(dailyMinutes),
      score: dates.reduce((sum, day) => sum + 2 ** (-age(day) / 14), 0),
      source,
      repeated: dates.length >= 2 && dayNumber(dates[0]) - dayNumber(dates[1]) === 7 && age(dates[0]) <= 7 };
  }).sort((a, b) => b.score - a.score || b.dates[0].localeCompare(a.dates[0]) || a.key.localeCompare(b.key));
  const candidate = candidates.find(item => item.repeated && !confirmed.some(rule => habitKey(rule) === item.key));
  const replacement = candidate && confirmed.length === 1
    && candidate.dates.slice(0, 2).every(day => !current.some(row => row.training_day === day && habitKey(row) === habitKey(confirmed[0])))
    && candidate.dates[1] > confirmed[0].decided_on ? confirmed[0] : undefined;
  const prompt: HabitPrompt | undefined = candidate ? { ...withoutKey(candidate), weekday, replace: replacement } : undefined;
  // Today's corrections outrank guesses. Another explicitly confirmed kind may still be logged.
  const loggedToday = history.filter(row => row.training_day === today);
  const routine = confirmed.find(item => (item.activity !== "sparring" || options.allowSparring)
    && !loggedToday.some(row => habitKey(row) === habitKey(item)));
  if (loggedToday.length && (!routine || loggedToday.some(row => !confirmed.some(item => habitKey(item) === habitKey(row))))) {
    return { ...none, prompt };
  }
  const learned = candidates.find(item => age(item.dates[0]) <= 14);
  const suggestion: HabitSuggestion | undefined = routine
    ? { ...routine, title: `Your usual ${HABIT_WEEKDAYS[weekday]}`, source: candidates.find(item => item.key === habitKey(routine))?.source }
    : learned ? { ...withoutKey(learned), title: "Suggested today" } : undefined;
  return { weekday, suggestion, prompt };
}

function withoutKey<T extends { key: string }>(item: T): Omit<T, "key"> {
  const { key: _key, ...rest } = item;
  return rest;
}

export function decideTrainingHabit(preferences: TrainingHabitPreferences, decision: TrainingHabitDecision, replace?: TrainingHabitDecision): TrainingHabitPreferences {
  const decisions = preferences.decisions.filter(item => !(item.weekday === decision.weekday && habitKey(item) === habitKey(decision)));
  return { ...preferences, decisions: [
    ...decisions.map(item => replace && item.weekday === replace.weekday && habitKey(item) === habitKey(replace)
      ? { ...item, state: "dismissed" as const, decided_on: decision.decided_on } : item), decision,
  ] };
}
