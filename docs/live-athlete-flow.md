# Live athlete daily flow

This document describes the live, day-to-day layer that turns UNLXCK from a
one-shot plan generator into a daily athlete operating system: persistent
plans, daily check-ins, session logs, injury flags, rule-based adaptations,
and the admin attention queue.

## Entity map

| Concept            | Where it lives                                                                 |
| ------------------ | ------------------------------------------------------------------------------ |
| athletes           | `profiles` (existing)                                                           |
| athlete profiles   | `profiles` + `athlete_intakes` (existing)                                       |
| training plans     | `plans` (existing — plans are persisted permanently at generation time)         |
| training weeks     | derived from `plans.planning_brief` via the weekly-schedule mapper (existing)   |
| training sessions  | derived per-day entries of the weekly schedule (existing)                       |
| daily check-ins    | `daily_checkins` (new)                                                          |
| session logs       | `session_logs` (new)                                                            |
| injury flags       | `injury_flags` (new)                                                            |
| adaptation notes   | `adaptation_notes` (new, append-only)                                           |
| generation jobs    | `generation_jobs` (existing, worker-owned)                                      |
| admin reviews      | `admin_reviews` (new)                                                           |

Weeks/sessions deliberately stay **derived** from the persisted plan rather
than being copied into their own tables: the generation pipeline owns that
structure, and duplicating it would create a second source of truth. Session
logs reference `plan_id` + `session_date` instead of a session row.

Migration: `supabase/migrations/20260611120000_add_live_athlete_daily_tracking.sql`
(also baked into `supabase/schema.sql`, enforced by the runtime schema gate via
`api/schema_requirements.py`). RLS matches the existing pattern: athletes read
their own rows, admins read everything, and **all writes go through the
service-role backend**. `admin_reviews` is admin-read-only.

## The daily loop

1. Athlete completes onboarding/intake (existing flow).
2. Worker generates the plan; the plan row is persisted permanently (existing).
3. `GET /api/dashboard` returns the live state: current plan, current week
   (resolved from calendar dates, falling back to weeks elapsed since plan
   creation for open-ended camps), today's session, next loaded session,
   readiness status, open injury flags, recent adaptation notes, and 7-day
   completion stats.
4. Athlete submits a daily check-in (`POST /api/checkins`) with 1–5 scales for
   readiness, fatigue, soreness, sleep quality, plus optional sleep hours,
   injury note, and notes. One row per athlete per UTC day (upsert).
5. Athlete logs sessions (`POST /api/session-logs`) with type, completed flag,
   RPE (1–10), and duration. Logs attach to the latest visible plan unless an
   explicit owned `plan_id` is supplied.
6. The safe rules layer (`api/readiness.py`) evaluates the new data and
   records every decision as an `adaptation_notes` row. Decisions that need a
   human open an `admin_reviews` row (deduped while one is already pending).
7. Admins work the queue at `GET /api/admin/reviews` and resolve items with
   `POST /api/admin/reviews/{id}/resolve`. Injury flags are resolved with
   `PATCH /api/admin/injury-flags/{id}`.

Nothing is overwritten silently: check-ins upsert by day, everything else is
append-only or status-transitioned, and any recommendation shown to the
athlete has an adaptation note explaining which rule fired.

## Readiness states

Computed server-side by `api.readiness.compute_readiness_summary` and stored
on each check-in (`daily_checkins.readiness_state`) for history:

| State          | Trigger                                                                     |
| -------------- | --------------------------------------------------------------------------- |
| `injury_flag`  | any open injury flag                                                         |
| `high_fatigue` | fatigue ≥ 4, soreness ≥ 4, readiness ≤ 2, or poor sleep (< 6h at quality ≤ 2) |
| `caution`      | moderate signals (any 3/5), poor sleep quality alone, a high-RPE streak, ≥ 2 recent missed sessions, or no check-in yet |
| `ready`        | everything in normal ranges                                                  |

## Safe adaptation rules (Phase 1 — no AI involved)

| Rule code               | Trigger                                        | Decision(s)                          |
| ----------------------- | ---------------------------------------------- | ------------------------------------ |
| `injury_reported`       | injury note on check-in / manual injury report | `swap_session` + `flag_admin_review` |
| `open_injury_flag`      | check-in while a flag is open                  | `swap_session` (keep substitutions)  |
| `high_fatigue_reduce_load` / `high_fatigue_add_recovery` | high-fatigue signals | `reduce_intensity` + `add_recovery`  |
| `repeated_high_rpe`     | RPE ≥ 8 on the last 3 completed sessions       | `reduce_intensity`                   |
| `missed_sessions`       | 2 missed in recent window (3 ⇒ review)         | `keep_plan` note / `flag_admin_review` |
| `checkin_ok` / `session_logged` | nothing unusual                        | `keep_plan`                          |

These rules adjust **recommendations and flags**, never the stored plan. A
future phase can feed `adaptation_notes` + logs into the generation pipeline
for AI-assisted plan regeneration; the worker-only generation model is
unchanged.

## API surface

Athlete (Bearer token, own data only):

- `GET  /api/dashboard` — full dashboard state
- `POST /api/checkins`, `GET /api/checkins?limit=`
- `POST /api/session-logs`, `GET /api/session-logs?limit=`
- `POST /api/injury-flags`, `GET /api/injury-flags?include_resolved=`

Admin only:

- `GET  /api/admin/reviews?status=pending|acknowledged|resolved|all`
- `POST /api/admin/reviews/{review_id}/resolve`
- `PATCH /api/admin/injury-flags/{flag_id}`
- `GET  /api/admin/athletes/{athlete_id}/daily-status`

## Frontend

- `/dashboard` — athlete daily page: readiness badge (Ready / Caution / High
  Fatigue / Injury Flag), today's and next session, check-in form, session-log
  form, week overview, recent adjustments. Linked as "Today" in the sidebar
  and mobile tab bar.
- `/admin` — "Needs attention" panel showing pending reviews with athlete
  context and one-click resolve, polling on the same interval as the
  generation queues.

## Tests

- `tests/test_readiness_rules.py` — unit tests for the readiness calculation
  and rule decisions.
- `tests/test_api_daily_flow.py` — API tests for check-in creation/upsert,
  session logging, dashboard retrieval, injury flagging, admin review queue
  and resolution, and plan persistence into the dashboard.
- `FakeStore` in `tests/support.py` mirrors the new store methods.
