// Synthetic evidence only. Shared by isolated browser regression/visual previews.
export const day = "2026-10-19";
export const asOf = `${day}T12:00:00Z`;
const shift = (value: string, offset: number) => new Date(Date.parse(`${value}T12:00:00Z`) + offset * 86400000).toISOString().slice(0, 10);
const counts = [3, 4, 2, 5, 4, 6, 4, 5];
const activities = ["boxing", "strength", "conditioning", "sparring", "roadwork"];
const titles = ["Boxing", "Strength & Power", "Conditioning", "Sparring", "Roadwork"];
export const sessions = counts.flatMap((count, week) => Array.from({ length: count }, (_, index) => ({
  id: `week-${week}-${index}`, source: index === 1 ? "unlxck" : "external", completion_origin: index === 1 ? "reported" : null,
  title: titles[index % titles.length], activity: index === 1 ? null : activities[index % activities.length],
  training_day: shift("2026-08-24", week * 7 + index), status: index === 1 ? "modified" : "done",
  duration_minutes: week >= 6 && index < 2 ? null : 50 + index * 5, effort: "moderate", plan_id: index === 1 ? "old-plan" : null,
}))).concat([{ id: "current", source: "external", completion_origin: null, title: "Boxing", activity: "boxing", training_day: day, status: "done", duration_minutes: 45, effort: "moderate", plan_id: null }]).sort((a, b) => b.training_day.localeCompare(a.training_day));

const performance = (id: string, date: string, value: number | null, unit = "kg") => ({
  id, training_day: date, performed_values: value === null ? null : { sets: 3, reps: 5, load: { value, unit } },
  block: { name: "Back Squat", kind: "exercise", status: value === null ? "skipped" : "modified",
    prescribed: { sets: 4, reps: 6, load: { display: "Choose a controlled load" } },
    actual: value === null ? {} : { sets: 3, reps: 5, load: { value, unit } },
    reason: value === null ? null : "fatigue", notes: "Kept each rep controlled.", responses: [], completed_dose: null },
});
export const performances = [
  performance("p6", "2026-10-19", 100), performance("p5", "2026-10-03", 95),
  performance("p4", "2026-09-15", 87.5), performance("gap", "2026-09-08", null),
  performance("p3", "2026-09-01", 85), performance("p2", "2026-08-17", 82.5), performance("p1", "2026-08-03", 80),
];
export const library = { as_of: asOf, coverage: "retained_logs", exercises: [
  { id: "key:back-squat", name: "Back Squat", identity_kind: "canonical", latest_day: day, latest_values: { sets: 3, reps: 5, load: { value: 100, unit: "kg" } }, latest_confirmed_as_prescribed: false,
    best_loads: [{ value: 100, unit: "kg", training_day: day, basis: "reported" }] },
  { id: "key:plank", name: "Plank", identity_kind: "canonical", latest_day: day, latest_values: { duration: { value: 60, unit: "seconds" } }, latest_confirmed_as_prescribed: false, best_loads: [] },
  { id: "key:push-ups", name: "Push-ups", identity_kind: "canonical", latest_day: day, latest_values: { reps: 20 }, latest_confirmed_as_prescribed: false, best_loads: [] },
  { id: "key:unmeasured", name: "Unmeasured hold", identity_kind: "canonical", latest_day: day, latest_values: {}, latest_confirmed_as_prescribed: true, best_loads: [] },
] };
export const me = { profile: { athlete_id: "00000000-0000-4000-8000-000000000001", email: "fighter@example.com", full_name: "Carlos", role: "athlete", access_status: "approved", technical_style: ["boxing"], tactical_style: [], athlete_timezone: "Europe/London", athlete_locale: "en", appearance_mode: "dark", nutrition_profile: {}, date_of_birth: "1995-01-01", meets_minimum_age: true, is_minor: false, terms_accepted: true, health_consent_granted: true, private_trial_ack_at: asOf }, plan_count: 0, latest_plan: null, latest_intake: null, username_rate_limit: {} };
export const auth = { access_token: "training-progress-test", refresh_token: "test", token_type: "bearer", expires_at: Date.parse(asOf) / 1000 + 864000,
  user: { id: me.profile.athlete_id, email: me.profile.email, aud: "authenticated", role: "authenticated", app_metadata: {}, user_metadata: {} } };

export function fixtureResponse(url: URL): { status?: number; body: unknown } {
  const path = url.pathname;
  if (path === "/api/me") return { body: me };
  if (path === "/api/training/history") return { body: url.searchParams.has("before_day") ? { sessions: sessions.filter(row => row.training_day < "2026-10-05"), next_before_day: null }
    : { sessions: sessions.filter(row => row.training_day >= "2026-10-05"), next_before_day: "2026-10-05" } };
  if (path.startsWith("/api/training/history/")) {
    const row = sessions.find(item => item.id === path.split("/").at(-1));
    return { body: { session: row, prescription_source: row?.source === "external" ? "manual" : "snapshot", blocks: row?.source === "external" ? [] : [performances[0].block] } };
  }
  if (path === "/api/history/exercise-library") return { body: library };
  if (path === "/api/history/exercise-performances") {
    const identity = url.searchParams.get("exercise");
    if (identity !== "key:back-squat") {
      const values = identity === "key:plank" ? [{ duration: { value: 45, unit: "seconds" } }, { duration: { value: 60, unit: "seconds" } }]
        : identity === "key:push-ups" ? [{ reps: 20 }] : [null];
      return { body: { performances: values.map((value, index) => ({ ...performance(`sparse-${index}`, shift(day, -7 + index * 7), null), performed_values: value,
        block: { ...performance("sparse", day, null).block, name: identity?.slice(4), status: "as_prescribed", actual: value ?? {}, prescribed: {} } })), next_cursor: null } };
    }
    return { body: url.searchParams.has("cursor") ? { performances: performances.slice(5), next_cursor: null } : { performances: performances.slice(0, 5), next_cursor: "older" } };
  }
  if (path === "/api/plans/active") return { status: 404, body: { detail: "No active plan" } };
  if (path === "/api/plans") return { body: [] };
  return { body: { notifications: [], unread_count: 0, level: 1, total_xp: 0, logs: [] } };
}
