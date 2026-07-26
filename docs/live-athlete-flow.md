# Live athlete daily flow

This document describes the live, day-to-day layer that turns UNLXCK from a
one-shot plan generator into a daily athlete operating system: persistent
plans, injury flags, rule-based adaptations, and the admin attention queue.

> **Status:** the athlete-facing daily loop moved to the Today surface
> (`GET /api/today`, `api/services/today_service.py`), which owns its own
> `today_checkins` and `session_completions` tables. The original
> `/api/dashboard`, `/api/checkins` and `/api/session-logs` endpoints described
> here were removed once nothing called them. The `daily_checkins` and
> `session_logs` tables still exist and hold historical rows, but no longer
> have an HTTP surface. Injury flags and the admin review queue below are
> current.

> **See also:** `docs/block-4-ux-hierarchy-addendum.md` locks the Today/Overview
> UX contracts (state-dependent landing, read-only Overview, recommendation TTL
> with athlete-local `day_rollover_hour = 04:00`, the check-in decision table,
> the thin completion model, risk-watch governance, and the normalized
> command-view read model). Where it touches the day boundary, that addendum
> refines the UTC-day check-in keying described here.

## Entity map

| Concept            | Where it lives                                                                 |
| ------------------ | ------------------------------------------------------------------------------ |
| athletes           | `profiles` (existing)                                                           |
| athlete profiles   | `profiles` + `athlete_intakes` (existing)                                       |
| training plans     | `plans` (existing — plans are persisted permanently at generation time)         |
| training weeks     | derived from `plans.planning_brief` via the weekly-schedule mapper (existing)   |
| training sessions  | derived per-day entries of the weekly schedule (existing)                       |
| daily check-ins    | `today_checkins` (`/api/today`); legacy `daily_checkins` retained, unused       |
| session logs       | `session_completions` (`/api/today`); legacy `session_logs` retained, unused    |
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
3. `GET /api/today` returns the live state: today's session, readiness,
   recommendation state, risk watch, and completion status. See
   `docs/block-4-ux-hierarchy-addendum.md` for that contract.
4. Athlete check-ins and session completions are submitted through the Today
   surface and stored in `today_checkins` / `session_completions`.
5. Athlete reports an injury (`POST /api/injury-flags`), which records the flag
   and opens an admin review.
6. Decisions are recorded as `adaptation_notes` rows; those needing a human
   open an `admin_reviews` row (deduped while one is already pending).
7. Admins work the queue at `GET /api/admin/reviews` and resolve items with
   `POST /api/admin/reviews/{id}/resolve`. Injury flags are resolved with
   `PATCH /api/admin/injury-flags/{id}`.

Nothing is overwritten silently: check-ins upsert by day, everything else is
append-only or status-transitioned, and any recommendation shown to the
athlete has an adaptation note explaining which rule fired.

## Readiness states

> Historical: these were computed by `api.readiness.compute_readiness_summary`
> for the removed `/api/dashboard` and `/api/checkins` endpoints and stored on
> `daily_checkins.readiness_state`. The Today surface computes its own
> readiness (`api/services/today_readiness_boundary.py`). The table below
> documents the legacy rules, which no longer run.

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

- `POST /api/injury-flags`, `GET /api/injury-flags?include_resolved=`
- `GET  /api/today` — the live daily surface (see the Block 4 addendum)

Admin only:

- `GET  /api/admin/reviews?status=pending|acknowledged|resolved|all`
- `POST /api/admin/reviews/{review_id}/resolve`
- `PATCH /api/admin/injury-flags/{flag_id}`

## Frontend

- `/today` — the athlete daily surface. `/dashboard` renders the same
  `TodayScreen`. Linked as "Today" in the sidebar and mobile tab bar.
- `/admin` — "Needs attention" panel showing pending reviews with athlete
  context and one-click resolve, polling on the same interval as the
  generation queues.

## Tests

- `tests/test_readiness_rules.py` — unit tests for the legacy readiness
  calculation and rule decisions in `api/readiness.py`. That module is now
  reachable only via `AdaptationDecision`; the rest is retained but unused.
- `tests/test_api_daily_flow.py` — API tests for injury flagging, the admin
  review queue, and review resolution.
- `tests/test_today_service.py` — the live daily surface.
- `FakeStore` in `tests/support.py` mirrors the store methods.
