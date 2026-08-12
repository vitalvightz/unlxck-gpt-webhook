# Fight-camp notification orchestration

The backend now evaluates source-backed notification intents as one athlete/day decision instead of independent reminder jobs. A routine training day may naturally produce 3–5 useful touches, but that is a healthy range rather than a quota. The engine never creates weight, fuel, hydration, or recovery filler solely to reach a count.

## Behaviour

- Routine pushes retain a hard six-per-training-day cap and 45-minute minimum spacing.
- Safety and source events have separate bounded caps (two and three per day respectively) and a 30-minute anti-burst interval.
- STOP replaces normal session touches. Modified-session copy replaces session-ready copy. Preparation compounds fuel and hydration. Simultaneous week, phase, plan, camp, and XP moments compound into one delivery.
- Completing a check-in, injury update, or session writes an action state and cancels pending/failed reminders for that exact athlete action.
- Training time resolves from athlete preference, authoritative session schedule, same-weekday history, session-type history, recent athlete history, then a configurable low-confidence fallback. Exact countdown copy is restricted to high-confidence timing.
- Plan publication is the only `plan_ready` trigger. Athlete-visible material changes can create `plan_updated`; structured-card-only changes do not.
- Routine and event notifications respect quiet hours. Deferred source events retain their original expiry and are released through normal event caps/spacing, preventing a wake-up backlog burst.
- Hydration, fuel, recovery, and weight retain distinct internal intents while temporarily mapping to existing preference categories.

## Diagnostics

Admins can query:

`GET /api/admin/notifications/diagnostics?athlete_id=<id>&training_day=YYYY-MM-DD&intent=<intent>`

The response contains coalesced evaluation facts with first/last timestamps, count, timing evidence, candidate source metadata, decision, rejection codes, template variant, and resulting delivery ID. Coalescing applies only when the intent, athlete training day, scheduled moment, candidate evidence, and decision are unchanged.

## Rollout

`UNLXCK_FIGHT_CAMP_NOTIFICATIONS_MODE` supports:

- `send` — new orchestration evaluates and delivers (default).
- `observe` — new orchestration records candidate decisions, then allows the existing delivery path to run.
- `legacy` — skips new orchestration and uses the existing delivery path.

`UNLXCK_NOTIFICATION_FALLBACK_TRAINING_TIME` configures the athlete-local, low-confidence fallback (`18:00` by default).

Apply `20260812155956_redesign_fight_camp_notifications.sql` before enabling `send`. The migration adds delivery metadata, templates, action states, evaluations, atomic claim/evaluation/action RPCs, RLS, and service-role-only grants. No production migration is applied by this branch.
